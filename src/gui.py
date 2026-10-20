import logging
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from config import DssConfig
from main import gee_workflow, dss_workflow



# Custom Handler para redirecionar logs para a caixa de texto da GUI
class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        
        def append_text():
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.see(tk.END)  # Auto-scroll para a última linha
            self.text_widget.configure(state='disabled')
            
        # Garante a atualização segura do widget a partir de threads secundárias
        self.text_widget.after(0, append_text)


class InterfaceWorkflow:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor de Processamento GEE & DSS")
        self.root.geometry("600x450")

        self.hms_file = tk.StringVar()
        hms_frame = ttk.Frame(root)
        hms_frame.pack(fill="x", padx=15, pady=(12, 4))
        ttk.Label(hms_frame, text="Projeto HEC-HMS (.hms):").pack(anchor="w")
        file_row = ttk.Frame(hms_frame)
        file_row.pack(fill="x", pady=(4, 0))
        ttk.Entry(file_row, textvariable=self.hms_file, state="readonly").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(file_row, text="Selecionar...", command=self.selecionar_hms).pack(
            side="left", padx=(8, 0)
        )

        # Botão para Iniciar o Processamento
        self.btn_run = tk.Button(
            root, 
            text="Iniciar Workflow", 
            bg="#28a745", 
            fg="white", 
            font=("Arial", 11, "bold"),
            command=self.iniciar_thread_processamento
        )
        self.btn_run.pack(pady=10)

        # Barra de Progresso (Indeterminada enquanto processa)
        self.progress_bar = ttk.Progressbar(root, mode='indeterminate')
        self.progress_bar.pack(fill='x', padx=15, pady=5)

        # Area de Texto para mostrar o progresso / logs em tempo real
        lbl_logs = tk.Label(root, text="Progresso do Processamento:", font=("Arial", 10, "bold"))
        lbl_logs.pack(anchor="w", padx=15, pady=(10, 0))

        self.txt_logs = scrolledtext.ScrolledText(root, height=15, state='disabled', font=("Consolas", 9))
        self.txt_logs.pack(fill='both', expand=True, padx=15, pady=10)

        # Configura o Logger para enviar os dados para a caixa de texto
        self.configurar_logger()

    def configurar_logger(self):
        # Captura o logger raiz ou o logger específico das tuas funções
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # Handler da interface
        handler_gui = TextHandler(self.txt_logs)
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%H:%M:%S')
        handler_gui.setFormatter(formatter)
        logger.addHandler(handler_gui)

    def iniciar_thread_processamento(self):
        selected_hms = self.hms_file.get()
        if not selected_hms:
            messagebox.showwarning("Projeto necessário", "Selecione o arquivo .hms do projeto.")
            return

        try:
            dss_config = DssConfig(hms_file=selected_hms)
        except (ValueError, FileNotFoundError) as error:
            messagebox.showerror("Projeto inválido", str(error))
            return

        # Desativa o botão e inicia a animação de progresso
        self.btn_run.config(state='disabled')
        self.progress_bar.start(10)
        
        # Executa as funções pesadas numa thread separada
        thread = threading.Thread(target=self.executar_workflows, args=(dss_config,))
        thread.daemon = True  # Encerra a thread caso a janela seja fechada
        thread.start()

    def selecionar_hms(self):
        path = filedialog.askopenfilename(
            title="Selecione o projeto HEC-HMS",
            filetypes=[("Projetos HEC-HMS", "*.hms"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self.hms_file.set(path)

    def executar_workflows(self, dss_config):
        try:
            logging.info("Iniciando o processo do Google Earth Engine (gee_workflow)...")
            gee_workflow()
            
            logging.info("Iniciando a geração do arquivo DSS (dss_workflow)...")
            dss_workflow(dss_config)

            logging.info("--- TODO O PROCESSAMENTO FOI CONCLUÍDO COM SUCESSO! ---")
            self.root.after(0, lambda: messagebox.showinfo("Sucesso", "Workflows executados com sucesso!"))

        except Exception as e:
            logging.error(f"Erro durante o processamento: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("Erro", f"Ocorreu uma falha:\n{str(e)}"))

        finally:
            # Reativa os botões e para a barra de progresso ao finalizar
            self.root.after(0, self.finalizar_processamento)

    def finalizar_processamento(self):
        self.progress_bar.stop()
        self.btn_run.config(state='normal')


if __name__ == "__main__":
    root = tk.Tk()
    app = InterfaceWorkflow(root)
    root.mainloop()
