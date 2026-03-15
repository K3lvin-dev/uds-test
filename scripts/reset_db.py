import subprocess
import sys


def main():
    print("--- Resetando Banco de Dados ---")

    terminate_cmds = (
        "SELECT pg_terminate_backend(pid) "
        "FROM pg_stat_activity "
        "WHERE datname = 'submissions_db' AND pid <> pg_backend_pid();"
    )

    cmds = [
        f'docker exec submissions_postgres psql -U postgres -d postgres -c "{terminate_cmds}"',
        "docker exec submissions_postgres psql -U postgres -d postgres -c 'DROP DATABASE IF EXISTS submissions_db;'",
        "docker exec submissions_postgres psql -U postgres -d postgres -c 'CREATE DATABASE submissions_db;'",
        "docker exec -i submissions_postgres psql -U postgres -d submissions_db < schema.sql",
    ]

    for cmd in cmds:
        print(f"Executando: {cmd}")
        res = subprocess.run(cmd, shell=True)
        if (
            res.returncode != 0
            and "DROP DATABASE" not in cmd
            and "pg_terminate_backend" not in cmd
        ):
            print("Falha ao resetar banco.")
            sys.exit(1)

    print("--- Banco de Dados Resetado ---")


if __name__ == "__main__":
    main()
