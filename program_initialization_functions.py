import toml
import re
import subprocess
import os
import platform

def read_rs_files(programs_path):
    # Check if the folder exists
    if not os.path.isdir(programs_path):
        print(f"The path '{programs_path}' does not exist.")
    else:
        # Get all .rs in the programs path
        file_names = [f for f in os.listdir(programs_path) if f.endswith(".rs")]

        # Read content of each file and store it in anchor_programs list
        anchor_programs = []
        for file_name in file_names:
            full_path = os.path.join(programs_path, file_name)
            with open(full_path, "r", encoding="utf-8") as f:
                anchor_programs.append(f.read())

        return file_names, anchor_programs

def compile_programs(file_names, programs):
    for file_name,program in zip(file_names,programs):
        print(f"Compiling program: {file_name}")

        # Remove .rs extension
        file_name_without_extension = file_name.removesuffix(".rs")

        # Compile program
        compile_program(file_name_without_extension, program)

        # Choose if deploy program
        print("Deploy compiled program? (y/n):")
        choice = input()
        if choice == "y":
            program_id = deploy_program(file_name_without_extension)
            # If deploy succeed, initialize anchorpy
            if program_id:
                initialize_anchorpy(program_id, file_name_without_extension)

def compile_program(program_name, program):
    # List of commands to be executed
    setup_commands = [
        f"mkdir -p .anchor_files/{program_name}", # Create folder for new program
        f"cd .anchor_files/{program_name}",  # # Change directory to new folder
        "anchor init anchor_environment",  # Initialize anchor environment
    ]
    build_commands = [
        f"cd ./.anchor_files/{program_name}/anchor_environment",  # Change directory to new anchor environment
        "anchor build"  # Build program
    ]

    # Merge commands with '&&' to execute them on the same shell
    setup_concatenated_command = " && ".join(setup_commands)
    build_concatenated_command = " && ".join(build_commands)
    if platform.system() == "Windows":
        run_compiling_commands_windows(setup_concatenated_command, build_concatenated_command, program_name, program)
    elif platform.system() == "Darwin" or platform.system() == "Linux":
        run_compiling_commands_macos_linux(setup_concatenated_command, build_concatenated_command, program_name, program)

def run_compiling_commands_windows(setup_concatenated_command, build_concatenated_command, program_name, program):
    # On Windows, use WSL to execute commands in a Linux shell
    print("Initializing Anchor project...")
    result = subprocess.run(["wsl", setup_concatenated_command], capture_output=True, text=True)
    if result.stderr:
        print(result.stderr)

    print("Building Anchor program, this may take a while... Please be patient.")
    write_program_in_lib_rs(program_name, program)
    impose_cargo_lock_version(program_name)
    result = subprocess.run(["wsl", build_concatenated_command], capture_output=True, text=True)
    if result.stderr:
        print(result.stderr)

def run_compiling_commands_macos_linux(setup_concatenated_command, build_concatenated_command, program_name, program):
    # On macOS and Linux, use default shell
    print("Initializing Anchor project...")
    result = subprocess.run(setup_concatenated_command, shell=True, capture_output=True, text=True)
    if result.stderr:
        print(result.stderr)

    print("Building Anchor program, this may take a while... Please be patient.")
    write_program_in_lib_rs(program_name, program)
    result = subprocess.run(build_concatenated_command, shell=True, capture_output=True, text=True)
    if result.stderr:
        # try by imposing cargo version 3
        try:
            impose_cargo_lock_version(program_name)
            result = subprocess.run(build_concatenated_command, shell=True, capture_output=True, text=True)
            if result.stderr:
                print(result.stderr)
        except:
            Exception('Error while building Anchor program')

def write_program_in_lib_rs(program_name, program):
    program = update_program_id(program_name, program)
    lib_rs_path = f".anchor_files/{program_name}/anchor_environment/programs/anchor_environment/src/lib.rs"
    with open(lib_rs_path, 'w') as file:
        file.write(program)

def impose_cargo_lock_version(program_name):
    file_path = f".anchor_files/{program_name}/anchor_environment/Cargo.lock"
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    with open(file_path, 'w', encoding='utf-8') as file:
        for line in lines:
            # Substitute each value of version with 3
            line = re.sub(r'^version = \d+', 'version = 3', line)
            file.write(line)

def update_program_id(program_name, program):
    file_path = f"./.anchor_files/{program_name}/anchor_environment/programs/anchor_environment/src/lib.rs"

    # Read program id generated by Anchor
    with open(file_path, 'r') as file:
        content = file.read()
        match = re.search(r'declare_id!\s*\(\s*"([^"]+)"\s*\)\s*;', content)
        if match:
            new_program_id = match.group(1)
        else:
            raise ValueError("Program ID not found in file")

    # Substitute program id in the file
    program = re.sub(r'declare_id!\s*\(\s*"([^"]+)"\s*\)\s*;', f'declare_id!("{new_program_id}");', program)
    return program

def deploy_program(program_name):
    file_path = "./solana_wallets/my_wallet.json"
    print("Place your wallet in the solana_wallets folder and rename it to my_wallet.json")
    # Check if wallet exists
    if not os.path.exists(file_path):
        print(f"File wallet.json not found")
        return

    # If wallet exists
    allowed_choices = ["1", "2", "3"]
    choice = None
    cluster = None
    program_id = None

    while choice not in allowed_choices:
        print("Where do you want to deploy program?")
        print("1. Localnet")
        print("2. Devnet")
        print("3. Mainnet")
        choice = input()
        if choice == "1":
            cluster = "Localnet"
        elif choice == "2":
            cluster = "Devnet"
        elif choice == "3":
            cluster = "Mainnet"
        else:
            print("Please insert a valid choice.")

    modify_cluster_wallet(cluster, program_name)
    # List of commands to be executed
    commands = [
        f"cd .anchor_files/{program_name}/anchor_environment/",  # Change directory to environment folder
        "anchor deploy",  # Deploy program
    ]

    # Merge commands with '&&' to execute them on the same shell
    concatenated_command = " && ".join(commands)
    if platform.system() == "Windows":
        program_id = run_deploying_commands_windows(concatenated_command)
    elif platform.system() == "Darwin" or platform.system() == "Linux":
        program_id = run_deploying_commands_macos_linux(concatenated_command)

    return program_id

def modify_cluster_wallet(cluster, program_name):
    file_path = f"./.anchor_files/{program_name}/anchor_environment/Anchor.toml"
    config = toml.load(file_path)

    # Edit values
    config['provider']['cluster'] = cluster
    config['provider']['wallet'] = "../../../solana_wallets/my_wallet.json"

    # Save modifications
    with open(file_path, 'w') as file:
        toml.dump(config, file)

def run_deploying_commands_windows(concatenated_command):
    # On Windows, use WSL to execute commands in a Linux shell
    print("Deploying program...")
    result = subprocess.run(["wsl", concatenated_command], capture_output=True, text=True)
    if result.stderr:
        print(result.stderr)
    else:
        program_id, signature = get_deploy_details(result.stdout)
        print("Deploy success")
        print(f"Program ID: {program_id}")
        print(f"Signature: {signature}")
        return program_id

def run_deploying_commands_macos_linux(concatenated_command):
    # On macOS and Linux, use default shell
    print("Deploying program...")
    result = subprocess.run(concatenated_command, shell=True, capture_output=True, text=True)
    if result.stderr:
        print(result.stderr)
    else:
        program_id, signature = get_deploy_details(result.stdout)
        print("Deploy success")
        print(f"Program ID: {program_id}")
        print(f"Signature: {signature}")
        return program_id

def get_deploy_details(output):
    # RegEx to find Program ID and signature
    program_id_pattern = r"Program Id: (\S+)"
    signature_pattern = r"Signature: (\S+)"

    # Find Program ID
    program_id_match = re.search(program_id_pattern, output)
    program_id = program_id_match.group(1) if program_id_match else None

    # Find Signature
    signature_match = re.search(signature_pattern, output)
    signature = signature_match.group(1) if signature_match else None

    return program_id, signature

def initialize_anchorpy(program_id, program_name):
    # Command to be executed
    idl_path = f".anchor_files/{program_name}/anchor_environment/target/idl/{program_name}.json"
    output_directory = f".anchor_files/{program_name}/anchorpy_files/"
    command = f"anchorpy client-gen {idl_path} {output_directory} --program-id {program_id}"

    if platform.system() == "Windows":
        run_initializing_anchorpy_commands_windows(command)
    elif platform.system() == "Darwin" or platform.system() == "Linux":
        run_initializing_anchorpy_commands_macos_linux(command)

def run_initializing_anchorpy_commands_windows(command):
    # On Windows, use WSL to execute commands in a Linux shell
    print("Initializing anchorpy...")
    result = subprocess.run(["wsl", command], capture_output=True, text=True)
    if result.stderr:
        print(result.stderr)
    else:
        print("Anchorpy initialized successfully")

def run_initializing_anchorpy_commands_macos_linux(command):
    # On macOS and Linux, use default shell
    print("Initializing anchorpy...")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    else:
        print("Anchorpy initialized successfully")
