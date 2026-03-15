import subprocess
import time
import sys

def run(cmd):
    print(f"Executando: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"Erro ao executar: {cmd}")
        sys.exit(1)

def main():
    print("--- Iniciando Infraestrutura ---")
    
    # 1. Sobe os containers
    run("docker compose up -d")
    
    # 2. Aguarda healthchecks
    print("Aguardando containers ficarem saudaveis...")
    for _ in range(30):
        result = subprocess.run("docker compose ps --format json", shell=True, capture_output=True, text=True)
        if '"Health":"healthy"' in result.stdout or "healthy" in result.stdout:
             # Verifica se ambos estao healthy (simplificado)
             if result.stdout.count("healthy") >= 2:
                 break
        time.sleep(2)
    
    print("--- Infraestrutura Pronta ---")

if __name__ == "__main__":
    main()
