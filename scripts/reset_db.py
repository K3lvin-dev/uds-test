import subprocess
import sys


def main():
    print("--- Resetando Banco de Dados ---")

    # Comando para derrubar todas as conexoes antes do DROP
    terminate_cmds = (
        "SELECT pg_terminate_backend(pid) "
        "FROM pg_stat_activity "
        "WHERE datname = 'submissions_db' AND pid <> pg_backend_pid();"
    )

    # Dropa e recria banco via docker
    cmds = [
        f'docker exec submissions_postgres psql -U postgres -d postgres -c "{terminate_cmds}"',  # noqa: E501
        "docker exec submissions_postgres psql -U postgres -d postgres -c 'DROP DATABASE IF EXISTS submissions_db;'",  # noqa: E501
        "docker exec submissions_postgres psql -U postgres -d postgres -c 'CREATE DATABASE submissions_db;'",  # noqa: E501
        "docker exec -i submissions_postgres psql -U postgres -d submissions_db < schema.sql",  # noqa: E501
    ]

    for cmd in cmds:
        print(f"Executando: {cmd}")
        res = subprocess.run(cmd, shell=True)
        if res.returncode != 0 and "DROP DATABASE" not in cmd:
            # Ignoramos erro no terminate caso o banco nem exista
            print("Falha ao resetar banco.")
            sys.exit(1)

    print("--- Banco de Dados Resetado ---")


if __name__ == "__main__":
    main()
