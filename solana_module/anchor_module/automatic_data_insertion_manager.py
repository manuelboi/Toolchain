# MIT License
#
# Copyright (c) 2025 Manuel Boi - Università degli Studi di Cagliari
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


import csv
import os
import re
from solders.pubkey import Pubkey
from anchorpy import Wallet, Provider
from solana_module.anchor_module.transaction_manager import build_transaction, measure_transaction_size, \
    compute_transaction_fees, send_transaction
from solana_module.solana_utils import load_keypair_from_file, solana_base_path, create_client, selection_menu
from solana_module.anchor_module.anchor_utils import anchor_base_path, find_initialized_programs, \
    find_program_instructions, find_required_accounts, find_signer_accounts, find_args, check_type, convert_type, \
    fetch_cluster, load_idl, check_if_array


# ====================================================
# PUBLIC FUNCTIONS
# ====================================================

async def run_execution_trace():
    # Fetch initialized programs
    initialized_programs = find_initialized_programs()
    if len(initialized_programs) == 0:
        print("No program has been initialized yet.")
        return

    results = []

    execution_traces = _find_execution_traces()
    file_name = selection_menu('execution trace', execution_traces)
    if file_name is None:
        return
    csv_file = _read_csv(f"{anchor_base_path}/execution_traces/{file_name}")

    # For each execution trace
    for index, row in enumerate(csv_file, start=1):
        # Separate values and remove spaces
        execution_trace = [x.strip() for x in re.split(r"[;,]", row[0])]

        # Get execution trace ID
        trace_id = execution_trace[0]
        print(f"Working on execution trace with ID {trace_id}...")

        # Manage program
        program_name = execution_trace[1]
        if program_name not in initialized_programs:
            print(f"Program {program_name} not initialized yet (execution trace {trace_id}).")
            return

        # Manage instruction
        idl_file_path = f'{anchor_base_path}/.anchor_files/{program_name}/anchor_environment/target/idl/{program_name}.json'
        idl = load_idl(idl_file_path)
        instructions = find_program_instructions(idl)
        instruction = execution_trace[2]
        if instruction not in instructions:
            print(f"Instruction {instruction} not found for the program {program_name} (execution trace {trace_id}).")

        # Manage accounts
        required_accounts = find_required_accounts(instruction, idl)
        signer_accounts = find_signer_accounts(instruction, idl)
        final_accounts = dict()
        signer_accounts_keypairs = dict()
        i = 3
        for account in required_accounts:
            # If it is a wallet
            if execution_trace[i].startswith("W:"):
                wallet_name = execution_trace[i].removeprefix('W:')
                file_path = f"{solana_base_path}/solana_wallets/{wallet_name}"
                keypair = load_keypair_from_file(file_path)
                if keypair is None:
                    print(f"Wallet for account {account} not found at path {file_path}.")
                    return
                if account in signer_accounts:
                    signer_accounts_keypairs[account] = keypair
                final_accounts[account] = keypair.pubkey()
            # If it is a PDA
            elif execution_trace[i].startswith("P:"):
                extracted_key = execution_trace[i].removeprefix('P:')
                pda_key = Pubkey.from_string(extracted_key)
                final_accounts[account] = pda_key
            else:
                print(f"Did not find 'W:' or 'P:' to indicate whether the cell contains a Wallet or a PDA.")
                return
            i += 1

        # Manage args
        required_args = find_args(instruction, idl)
        final_args = dict()
        for arg in required_args:
            # Manage arrays
            array_type, array_length = check_if_array(arg)
            if array_type is not None and array_length is not None:
                array_values = execution_trace[i].split()

                # Check if array has correct length
                if len(array_values) != array_length:
                    print(f"Error: Expected array of length {array_length}, but got {len(array_values)}")
                    return

                # Convert array elements basing on the type
                valid_values = []
                for j in range(len(array_values)):
                    converted_value = convert_type(array_type, array_values[j])
                    if converted_value is not None:
                        valid_values.append(converted_value)
                    else:
                        print(f"Invalid input at index {j}. Please try again.")
                        return

                final_args[arg['name']] = valid_values

            # Manage classical args
            else:
                type = check_type(arg["type"])
                if type is None:
                    print(f"Unsupported type for arg {arg['name']}")
                    return
                converted_value = convert_type(type, execution_trace[i])
                final_args[arg['name']] = converted_value

            i += 1

        # Manage provider
        provider_keypair_path = f"{solana_base_path}/solana_wallets/{execution_trace[i]}"
        keypair = load_keypair_from_file(provider_keypair_path)
        if keypair is None:
            print("Provider wallet not found.")
        cluster = fetch_cluster(program_name)
        client = create_client(cluster)
        provider_wallet = Wallet(keypair)
        provider = Provider(client, provider_wallet)

        # Manage transaction
        transaction = await build_transaction(program_name, instruction, final_accounts, final_args, signer_accounts_keypairs, client, provider)
        size = measure_transaction_size(transaction)
        fees = await compute_transaction_fees(client, transaction)

        # CSV building
        csv_row = [trace_id, size, fees]

        i += 1
        if execution_trace[i].lower() == 'true':
            transaction_hash = await send_transaction(provider, transaction)
            csv_row.append(transaction_hash)

        # Append results
        results.append(csv_row)
        print(f"Execution trace {index} results computed!")

    # CSV writing
    file_name_without_extension = file_name.removesuffix(".csv")
    file_path = _write_csv(file_name_without_extension, results)
    print(f"Results written successfully to {file_path}")





# ====================================================
# PRIVATE FUNCTIONS
# ====================================================

def _find_execution_traces():
    path = f"{anchor_base_path}/execution_traces/"
    if not os.path.exists(path):
        print(f"Error: Folder '{path}' does not exist.")
        return []

    return [f for f in os.listdir(path) if f.lower().endswith('.csv')]

def _read_csv(file_path):
    if os.path.exists(file_path):
        with open(file_path, mode='r') as file:
            csv_file = csv.reader(file)
            return list(csv_file)
    else:
        return None

def _write_csv(file_name, results):
    folder = f'{anchor_base_path}/execution_traces_results/'
    csv_file = os.path.join(folder, f'{file_name}_results.csv')

    # Create folder if it doesn't exist
    os.makedirs(folder, exist_ok=True)

    # Write CSV file
    with open(csv_file, mode='w', newline='') as file:
        csv_writer = csv.writer(file)
        for row in results:
            csv_writer.writerow(row)
    return csv_file