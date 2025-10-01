# simulador_contemp.py

import time
import random
from threading import Thread
from pyModbusTCP.server import ModbusServer, DataBank

# --- Configurações do Simulador ---
SERVER_HOST = "localhost"
SERVER_PORT = 502

# --- Configurações da Simulação Física da Estufa ---
TEMP_AMBIENTE = 28.0  # Temperatura externa em °C

class GreenhouseSimulator:
    """
    Esta classe simula a dinâmica da temperatura de uma estufa
    e a lógica de um controlador de temperatura individual.
    """
    def __init__(self, name, server_data_bank, register_offset, initial_temp, taxa_perda, taxa_aquecimento):
        self.name = name
        self.datobank = server_data_bank
        self.offset = register_offset
        
        # Estado interno da simulação
        self.temperatura_atual = initial_temp
        self.taxa_perda_calor = taxa_perda
        self.taxa_aquecimento = taxa_aquecimento

        # Inicializa os valores no DataBank do Modbus
        # Multiplicamos por 10 para trabalhar com uma casa decimal
        # Regs: 0:SP, 1:PV, 2:Saída, 3:Histerese, 4:Modo, 5:Intervalo(s)
        self.datobank.set_holding_registers(self.offset, [250, int(self.temperatura_atual * 10), 0, 10, 1, 5])

    def update(self):
        """Executa um único passo da simulação."""
        # 1. Ler parâmetros do controlador (do Modbus DataBank)
        # Dividimos por 10 para obter o valor real
        setpoint = self.datobank.get_holding_registers(self.offset + 0, 1)[0] / 10.0
        histerese = self.datobank.get_holding_registers(self.offset + 3, 1)[0] / 10.0
        
        # 2. Lógica de Controle (On/Off com Histerese)
        output_state = self.datobank.get_holding_registers(self.offset + 2, 1)[0]
        if self.temperatura_atual < (setpoint - histerese):
            new_output_state = 1
        elif self.temperatura_atual > (setpoint + histerese):
            new_output_state = 0
        else:
            new_output_state = output_state

        # 3. Simular a Física da Estufa
        diferenca_temp = self.temperatura_atual - TEMP_AMBIENTE
        self.temperatura_atual -= diferenca_temp * self.taxa_perda_calor
        if new_output_state == 1:
            self.temperatura_atual += self.taxa_aquecimento
        self.temperatura_atual += random.uniform(-0.05, 0.05)

        # 4. Atualizar os registros Modbus para o cliente ler
        self.datobank.set_holding_registers(self.offset + 1, [int(self.temperatura_atual * 10)]) # PV
        self.datobank.set_holding_registers(self.offset + 2, [new_output_state]) # Saída

        # Imprime o status no console para depuração
        print(
            f"[{self.name}] SP: {setpoint:.1f}°C | "
            f"PV: {self.temperatura_atual:.1f}°C | "
            f"Saída: {'LIGADA' if new_output_state == 1 else 'DESLIGADA'}"
        )

if __name__ == '__main__':
    # Inicia o servidor Modbus
    print(f"Iniciando servidor Modbus TCP em {SERVER_HOST}:{SERVER_PORT}...")
    server = ModbusServer(host=SERVER_HOST, port=SERVER_PORT, no_block=True)

    try:
        server.start()
        print("Servidor Modbus em execução.")
        
        # Cria duas instâncias de simuladores com parâmetros diferentes
        simulador1 = GreenhouseSimulator(
            name="Estufa 1", server_data_bank=server.data_bank, register_offset=0,
            initial_temp=20.0, taxa_perda=0.1, taxa_aquecimento=0.2
        )
        simulador2 = GreenhouseSimulator(
            name="Estufa 2", server_data_bank=server.data_bank, register_offset=10,
            initial_temp=25.0, taxa_perda=0.05, taxa_aquecimento=0.15
        )

        # Loop principal que atualiza ambos os simuladores
        while True:
            # O intervalo é lido do registro do primeiro simulador, mas poderia ser individual
            intervalo_s = server.data_bank.get_holding_registers(5, 1)[0]
            if intervalo_s <= 0: intervalo_s = 1 # Evita loop infinito

            simulador1.update()
            simulador2.update()
            print("-" * 60)
            time.sleep(intervalo_s)

    except KeyboardInterrupt:
        print("Encerrando o servidor e o simulador...")
        server.stop()
        print("Servidor e simulador encerrados.")
