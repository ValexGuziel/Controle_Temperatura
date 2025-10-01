# cliente_modbus.py

from pyModbusTCP.client import ModbusClient
import time

# --- Configurações do Cliente ---
SERVER_HOST = "localhost"
SERVER_PORT = 502
CLIENT_ID = 1 # ID do escravo Modbus (geralmente 1)

# --- Endereços dos Registros (conforme o simulador) ---
REG_SETPOINT = 0
REG_PV = 1
REG_OUTPUT = 2

# Instancia o cliente
# auto_open=True garante que ele tentará se conectar assim que for criado
client = ModbusClient(host=SERVER_HOST, port=SERVER_PORT, unit_id=CLIENT_ID, auto_open=True)

def read_data():
    """Lê os dados do servidor Modbus e os exibe."""
    if not client.is_open:
        print("Falha na conexão. Tentando reconectar...")
        if not client.open():
            print("Não foi possível reconectar.")
            return False

    # Lê múltiplos registros de uma vez para ser mais eficiente
    # Vamos ler 3 registros a partir do endereço 0 (Setpoint, PV, Saída)
    regs = client.read_holding_registers(REG_SETPOINT, 3)
    
    if regs:
        setpoint = regs[0] / 10.0
        pv = regs[1] / 10.0
        output_state = "LIGADA" if regs[2] == 1 else "DESLIGADA"
        
        print(f"Status -> Setpoint: {setpoint:.1f}°C | Temp. Atual (PV): {pv:.1f}°C | Saída: {output_state}")
        return True
    else:
        print("Falha ao ler registros do servidor.")
        return False

def write_setpoint(new_sp):
    """Escreve um novo valor de Setpoint no servidor."""
    if not client.is_open:
        print("Não é possível escrever: cliente não conectado.")
        return

    try:
        sp_value = float(new_sp)
        # Multiplicamos por 10 para enviar como inteiro, conforme a lógica do simulador
        sp_register_value = int(sp_value * 10)
        
        print(f"Enviando novo Setpoint: {sp_value:.1f}°C (Valor no registro: {sp_register_value})")
        
        if client.write_single_register(REG_SETPOINT, sp_register_value):
            print("Setpoint atualizado com sucesso!")
        else:
            print("Falha ao atualizar o Setpoint.")

    except ValueError:
        print("Entrada inválida. Por favor, insira um número (ex: 28.5).")

if __name__ == '__main__':
    print("--- Cliente de Controle da Estufa ---")
    print("Pressione Enter para atualizar os dados ou digite um novo Setpoint e pressione Enter.")
    print("Pressione Ctrl+C para sair.")
    
    try:
        while True:
            # Lê e exibe os dados atuais
            read_data()
            
            # Aguarda por entrada do usuário por 5 segundos
            try:
                new_input = input("Novo Setpoint (ou Enter): ")
                if new_input:
                    write_setpoint(new_input)
                # Adiciona uma pequena pausa após a escrita para o servidor processar
                time.sleep(1) 
            except EOFError:
                # Permite que o script continue se for executado de forma não interativa
                time.sleep(5)

    except KeyboardInterrupt:
        print("\nEncerrando o cliente...")
    finally:
        client.close()
        print("Conexão fechada.")
