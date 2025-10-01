# cliente_gui.py

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
from pyModbusTCP.client import ModbusClient
import threading
from collections import deque
import csv
import os
import webbrowser
import tempfile
from datetime import datetime
 
# --- Imports para o Gráfico ---
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

# --- Configurações do Cliente Modbus ---
SERVER_HOST = "localhost"
SERVER_PORT = 502
CLIENT_ID = 1

# --- Definições de Registros (relativos ao offset) ---
REG_SETPOINT_REL = 0
REG_PV_REL = 1
REG_OUTPUT_REL = 2
REG_INTERVALO_REL = 5

class ControllerTab(ttk.Frame):
    """
    Representa uma única aba na interface, controlando um simulador de estufa.
    """
    def __init__(self, parent, client, name, register_offset):
        super().__init__(parent)
        self.client = client
        self.name = name
        self.register_offset = register_offset

        # --- Variáveis de Controle do Tkinter ---
        self.pv_var = tk.StringVar(value="-- °C")
        self.sp_var = tk.StringVar(value="-- °C")
        self.output_var = tk.StringVar(value="DESCONHECIDO")
        self.new_sp_var = tk.StringVar()
        self.logging_status_var = tk.StringVar(value="Log: Inativo")

        # --- Controle de Log ---
        self.is_logging = False
        self.log_filepath = None

        # --- Armazenamento de dados para o gráfico ---
        self.MAX_POINTS = 50
        self.pv_history = deque(maxlen=self.MAX_POINTS)
        self.sp_history = deque(maxlen=self.MAX_POINTS)
        self.time_steps = deque(maxlen=self.MAX_POINTS)

        self.create_widgets()

    def create_widgets(self):
        # Frame de controle (à esquerda)
        control_frame = ttk.LabelFrame(self, text=f"Controles - {self.name}", padding="10")
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10), pady=5)

        # Frame do gráfico (à direita)
        graph_frame = ttk.LabelFrame(self, text=f"Histórico - {self.name}", padding="10")
        graph_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, pady=5)

        # --- Display de Dados ---
        ttk.Label(control_frame, text="Temperatura Atual (PV):").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Label(control_frame, textvariable=self.pv_var, font=("Helvetica", 14, "bold")).grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Label(control_frame, text="Setpoint (SP):").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Label(control_frame, textvariable=self.sp_var, font=("Helvetica", 12)).grid(row=3, column=0, sticky="w", pady=(0, 10))
        ttk.Label(control_frame, text="Estado da Saída:").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Label(control_frame, textvariable=self.output_var, font=("Helvetica", 12)).grid(row=5, column=0, sticky="w", pady=(0, 20))

        # --- Entrada de Dados ---
        ttk.Label(control_frame, text="Novo Setpoint:").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Entry(control_frame, textvariable=self.new_sp_var, width=15).grid(row=7, column=0, sticky="ew")
        ttk.Button(control_frame, text="Atualizar Setpoint", command=self.write_new_setpoint).grid(row=8, column=0, pady=10, sticky="ew")

        # --- Log ---
        self.log_button = ttk.Button(control_frame, text="Iniciar Log", command=self.toggle_logging)
        self.log_button.grid(row=9, column=0, pady=(0, 10), sticky="ew")
        ttk.Label(control_frame, textvariable=self.logging_status_var, font=("Helvetica", 8)).grid(row=10, column=0, sticky="w")

        # --- Relatório ---
        report_button = ttk.Button(control_frame, text="Gerar Relatório", command=self.open_report_window)
        report_button.grid(row=11, column=0, pady=(10, 0), sticky="ew")

        # --- Gráfico ---
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.fig.tight_layout()

    def update_display(self, regs, current_time):
        """Atualiza a interface da aba com novos dados."""
        if not regs:
            return
            
        sp = regs[REG_SETPOINT_REL] / 10.0
        pv = regs[REG_PV_REL] / 10.0
        output_state = regs[REG_OUTPUT_REL]

        self.sp_var.set(f"{sp:.1f} °C")
        self.pv_var.set(f"{pv:.1f} °C")
        self.output_var.set("LIGADA" if output_state == 1 else "DESLIGADA")

        self.pv_history.append(pv)
        self.sp_history.append(sp)
        self.time_steps.append(current_time)

        self.update_plot()

        if self.is_logging:
            self.append_to_log(current_time, pv, sp, output_state)

    def update_plot(self):
        self.ax.clear()
        self.ax.plot(self.time_steps, self.pv_history, marker='o', linestyle='-', markersize=4, label='Temperatura (PV)')
        self.ax.plot(self.time_steps, self.sp_history, linestyle='--', color='r', label='Setpoint (SP)')
        self.ax.set_title("Histórico de Temperatura")
        self.ax.set_xlabel("Horário")
        self.ax.set_ylabel("Temperatura (°C)")
        self.ax.grid(True)
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.fig.autofmt_xdate()
        self.ax.legend()
        self.canvas.draw()

    def write_new_setpoint(self):
        try:
            sp_value = float(self.new_sp_var.get().replace(',', '.'))
            sp_register_value = int(sp_value * 10)
            reg_addr = self.register_offset + REG_SETPOINT_REL
            threading.Thread(target=self._write_task, args=(reg_addr, sp_register_value)).start()
        except ValueError:
            messagebox.showerror("Erro de Entrada", "Por favor, insira um valor numérico válido.")
            self.new_sp_var.set("")

    def _write_task(self, address, value):
        if self.client.write_single_register(address, value):
            self.new_sp_var.set("")
        else:
            messagebox.showerror("Erro de Escrita", f"Falha ao atualizar Setpoint para {self.name}")

    def toggle_logging(self):
        if self.is_logging:
            self.is_logging = False
            self.log_button.config(text="Iniciar Log")
            self.logging_status_var.set("Log: Inativo")
        else:
            filepath = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                title=f"Salvar log para {self.name}",
                initialfile=f"log_{self.name.replace(' ', '_').lower()}.csv"
            )
            if not filepath: return
            
            self.log_filepath = filepath
            self.is_logging = True
            self.log_button.config(text="Parar Log")
            self.logging_status_var.set(f"Log: {self.log_filepath.split('/')[-1]}")
            try:
                # Verifica se o arquivo já existe e não está vazio
                file_exists = os.path.isfile(self.log_filepath) and os.path.getsize(self.log_filepath) > 0
                
                # Abre o arquivo em modo de 'append' (adicionar ao final)
                with open(self.log_filepath, 'a', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    if not file_exists: # Só escreve o cabeçalho se o arquivo for novo
                        writer.writerow(['Horário', 'Temperatura (°C)', 'Setpoint (°C)', 'Saida (0=OFF, 1=ON)'])
            except IOError as e:
                messagebox.showerror("Erro de Arquivo", f"Não foi possível criar o arquivo de log:\n{e}")
                self.is_logging = False

    def append_to_log(self, time, pv, sp, output_state):
        try:
            with open(self.log_filepath, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([time.strftime('%d/%m/%Y %H:%M:%S'), f"{pv:.2f}", f"{sp:.1f}", output_state])
        except IOError as e:
            print(f"Erro de log para {self.name}: {e}")

    def open_report_window(self):
        log_file = filedialog.askopenfilename(
            title=f"Selecione o arquivo de log para {self.name}",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if log_file:
            ReportWindow(self.winfo_toplevel(), log_file, self.name)


class GreenhouseControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Painel de Controle de Estufas")
        self.root.geometry("850x600")

        self.status_var = tk.StringVar(value="Conectando...")
        self.intervalo_leitura_ms = 5000
        self.interval_options = {"5 segundos": 5, "10 segundos": 10, "15 segundos": 15, "20 segundos": 20, "30 segundos": 30}

        self.client = ModbusClient(host=SERVER_HOST, port=SERVER_PORT, unit_id=CLIENT_ID, auto_open=True)
        
        self.create_widgets()
        self.update_data()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # --- Frame Superior para Controles Globais ---
        top_frame = ttk.Frame(self.root, padding=(10, 10, 10, 0))
        top_frame.pack(fill=tk.X)

        interval_frame = ttk.LabelFrame(top_frame, text="Intervalo de Leitura Global", padding="5")
        interval_frame.pack(side=tk.LEFT)
        self.interval_combo = ttk.Combobox(interval_frame, values=list(self.interval_options.keys()), state="readonly")
        self.interval_combo.pack(side=tk.LEFT)
        self.interval_combo.set("5 segundos")
        ttk.Button(interval_frame, text="Aplicar", command=self.apply_new_interval, width=8).pack(side=tk.LEFT, padx=(5,0))

        # --- Notebook para as Abas ---
        notebook = ttk.Notebook(self.root, padding=(10, 5, 10, 5))
        notebook.pack(fill=tk.BOTH, expand=True)

        self.tab1 = ControllerTab(notebook, self.client, "Estufa 1", register_offset=0)
        self.tab2 = ControllerTab(notebook, self.client, "Estufa 2", register_offset=10)
        
        notebook.add(self.tab1, text="Estufa 1")
        notebook.add(self.tab2, text="Estufa 2")

        # --- Barra de Status ---
        status_label = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w", padding=2)
        status_label.pack(fill=tk.X)

    def update_data(self):
        if not self.client.is_open:
            self.status_var.set("Reconectando...")
            self.client.open()
        
        if self.client.is_open:
            # Lê dados para ambas as estufas
            regs1 = self.client.read_holding_registers(self.tab1.register_offset, 6)
            regs2 = self.client.read_holding_registers(self.tab2.register_offset, 6)
            
            if regs1 and regs2:
                self.status_var.set("Conectado")
                current_time = datetime.now()
                self.tab1.update_display(regs1, current_time)
                self.tab2.update_display(regs2, current_time)
            else:
                self.status_var.set("Erro de leitura Modbus")
        else:
            self.status_var.set("Falha na conexão")

        self.root.after(self.intervalo_leitura_ms, self.update_data)

    def apply_new_interval(self):
        selection = self.interval_combo.get()
        new_interval_s = self.interval_options[selection]
        self.intervalo_leitura_ms = new_interval_s * 1000

        # Envia o novo intervalo para ambos os controladores
        # Nota: O simulador atual usa um intervalo global, então escrever em um já basta.
        # Escrevemos em ambos para um design mais robusto.
        threading.Thread(target=self._write_interval_task, args=(self.tab1.register_offset + REG_INTERVALO_REL, new_interval_s)).start()
        threading.Thread(target=self._write_interval_task, args=(self.tab2.register_offset + REG_INTERVALO_REL, new_interval_s)).start()
        self.status_var.set(f"Intervalo global definido para {new_interval_s}s")

    def _write_interval_task(self, address, interval_s):
        if not self.client.write_single_register(address, interval_s):
            self.status_var.set(f"Falha ao atualizar intervalo no endereço {address}.")

    def on_closing(self):
        if messagebox.askokcancel("Sair", "Deseja fechar a aplicação?"):
            self.client.close()
            self.root.destroy()

class ReportWindow(tk.Toplevel):
    """Janela para configurar e exibir o relatório."""
    def __init__(self, parent, log_filepath, controller_name):
        super().__init__(parent)
        self.log_filepath = log_filepath
        self.controller_name = controller_name
        self.filtered_data = []

        self.title(f"Relatório - {controller_name}")
        self.geometry("400x200")

        self.start_time_var = tk.StringVar()
        self.end_time_var = tk.StringVar()

        self.create_widgets()

    def create_widgets(self):
        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Gerar relatório do arquivo:").pack(anchor="w")
        ttk.Label(frame, text=self.log_filepath.split('/')[-1], font=("Helvetica", 8, "italic")).pack(anchor="w", pady=(0, 10))

        ttk.Label(frame, text="Data/Hora Início (DD/MM/AAAA HH:MM:SS):").pack(anchor="w")
        ttk.Entry(frame, textvariable=self.start_time_var).pack(fill=tk.X)

        ttk.Label(frame, text="Data/Hora Fim (DD/MM/AAAA HH:MM:SS):").pack(anchor="w", pady=(5, 0))
        ttk.Entry(frame, textvariable=self.end_time_var).pack(fill=tk.X)

        ttk.Button(frame, text="Gerar Relatório", command=self.generate_report).pack(pady=15)

    def generate_report(self):
        try:
            start_time_str = self.start_time_var.get()
            end_time_str = self.end_time_var.get()
            
            if not start_time_str or not end_time_str:
                messagebox.showerror("Erro", "Por favor, preencha as datas de início e fim.", parent=self)
                return

            start_time = datetime.strptime(start_time_str, '%d/%m/%Y %H:%M:%S')
            end_time = datetime.strptime(end_time_str, '%d/%m/%Y %H:%M:%S')
        except ValueError:
            messagebox.showerror("Erro de Formato", "Formato de data/hora inválido. Use DD/MM/AAAA HH:MM:SS.", parent=self)
            return

        self.filtered_data = []
        temperatures = []

        try:
            with open(self.log_filepath, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                header = next(reader) # Pula o cabeçalho
                self.filtered_data.append(header)

                for row in reader:
                    row_time = datetime.strptime(row[0], '%d/%m/%Y %H:%M:%S')
                    if start_time <= row_time <= end_time:
                        self.filtered_data.append(row)
                        temperatures.append(float(row[1]))
        except (IOError, IndexError, ValueError) as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível ler ou processar o arquivo de log:\n{e}", parent=self)
            return

        if not temperatures:
            messagebox.showinfo("Relatório", "Nenhum dado encontrado para o período especificado.", parent=self)
            return

        # Calcular estatísticas
        avg_temp = sum(temperatures) / len(temperatures)
        max_temp = max(temperatures)
        min_temp = min(temperatures)

        # Exibir resultados
        self.show_results_window(avg_temp, max_temp, min_temp)

    def show_results_window(self, avg, maxi, mini):
        results_win = tk.Toplevel(self)
        results_win.title(f"Resultados do Relatório - {self.controller_name}")
        results_win.geometry("600x400")

        stats_frame = ttk.LabelFrame(results_win, text="Estatísticas do Período", padding="10")
        stats_frame.pack(fill=tk.X, padx=10, pady=10)
        stats_text = (f"Temperatura Média: {avg:.2f}°C\n"
                      f"Temperatura Máxima: {maxi:.2f}°C\n"
                      f"Temperatura Mínima: {mini:.2f}°C")
        ttk.Label(stats_frame, text=stats_text, justify=tk.LEFT).pack(anchor="w")

        data_frame = ttk.LabelFrame(results_win, text="Dados Filtrados", padding="10")
        data_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        tree = ttk.Treeview(data_frame, columns=self.filtered_data[0], show='headings')
        for col in self.filtered_data[0]:
            tree.heading(col, text=col)
            tree.column(col, width=120)
        for row in self.filtered_data[1:]:
            tree.insert('', tk.END, values=row)
        tree.pack(fill=tk.BOTH, expand=True)

        ttk.Button(results_win, text="Salvar este relatório em CSV", command=self.save_filtered_report).pack(pady=10)
        ttk.Button(results_win, text="Imprimir Relatório", command=self.print_report).pack(pady=(0, 10))


    def save_filtered_report(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")], title="Salvar Relatório Filtrado")
        if not filepath: return
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(self.filtered_data)
        messagebox.showinfo("Sucesso", "Relatório salvo com sucesso!", parent=self)

    def print_report(self):
        """Gera um arquivo HTML do relatório e o abre no navegador para impressão."""
        try:
            # Gerar conteúdo HTML
            html = "<html><head><title>Relatório de Temperatura</title>"
            html += "<style>"
            html += "body { font-family: sans-serif; }"
            html += "table { border-collapse: collapse; width: 100%; }"
            html += "th, td { border: 1px solid #dddddd; text-align: left; padding: 8px; }"
            html += "tr:nth-child(even) { background-color: #f2f2f2; }"
            html += "h1, h2 { color: #333; }"
            html += "</style></head><body>"
            
            html += f"<h1>Relatório de Temperatura - {self.controller_name}</h1>"
            
            # Re-calcular estatísticas para garantir que estão disponíveis
            temperatures = [float(row[1]) for row in self.filtered_data[1:]]
            avg_temp = sum(temperatures) / len(temperatures)
            max_temp = max(temperatures)
            min_temp = min(temperatures)

            html += "<h2>Estatísticas do Período</h2>"
            html += f"<p><b>Temperatura Média:</b> {avg_temp:.2f}°C</p>"
            html += f"<p><b>Temperatura Máxima:</b> {max_temp:.2f}°C</p>"
            html += f"<p><b>Temperatura Mínima:</b> {min_temp:.2f}°C</p>"

            html += "<h2>Dados Registrados</h2>"
            html += "<table><tr>"
            for header in self.filtered_data[0]:
                html += f"<th>{header}</th>"
            html += "</tr>"
            for row in self.filtered_data[1:]:
                html += "<tr>"
                for cell in row:
                    html += f"<td>{cell}</td>"
                html += "</tr>"
            html += "</table></body></html>"

            # Salvar em arquivo temporário e abrir no navegador
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
                f.write(html)
                webbrowser.open_new_tab(f'file://{f.name}')
        except Exception as e:
            messagebox.showerror("Erro de Impressão", f"Não foi possível gerar o relatório para impressão:\n{e}", parent=self)

if __name__ == "__main__":
    root = tk.Tk()
    app = GreenhouseControlApp(root)
    root.mainloop()
