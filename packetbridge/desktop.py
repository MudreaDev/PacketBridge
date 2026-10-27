"""Visible host controls, plus a browser-client launcher on Windows and macOS."""
import sys
import queue
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from .agent import Agent
from .protocol import relay_url


class App:
    def __init__(self, root):
        self.root, self.backend, self.agent = root, None, None
        self.events = queue.Queue()
        self.rows = []
        root.title('PacketBridge · Colaborare Packet Tracer')
        root.geometry('760x650')
        root.minsize(650, 580)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', padding=9)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='PacketBridge', font=('Arial', 26, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='O sesiune de lucru. Doar ferestrele Packet Tracer aprobate.').pack(anchor='w', pady=(4, 18))
        ttk.Label(frame, text='Adresa serverului (aceeași la ambii participanți)').pack(anchor='w')
        self.url = tk.StringVar(value='http://127.0.0.1:8765')
        ttk.Entry(frame, textvariable=self.url).pack(fill='x', pady=6)
        ttk.Button(frame, text='Conectează-te ca participant · deschide clientul', command=self.client).pack(fill='x')
        ttk.Separator(frame).pack(fill='x', pady=18)
        ttk.Label(frame, text='Găzduiește pe Windows', font=('Arial', 15, 'bold')).pack(anchor='w')
        self.list = tk.Listbox(frame, selectmode='extended', exportselection=False, height=6)
        self.list.pack(fill='both', expand=True, pady=8)
        bar = ttk.Frame(frame)
        bar.pack(fill='x')
        ttk.Button(bar, text='Actualizează ferestrele', command=self.refresh).pack(side='left')
        ttk.Button(bar, text='Partajează selecția', command=self.grant).pack(side='left', padx=8)
        if sys.platform == 'win32':
            ttk.Button(bar, text='Partajează toate ferestrele Packet Tracer', command=self.start_packettracer_session).pack(side='left', padx=8)
        if sys.platform == 'win32':
            ttk.Button(bar, text='Partajează desktopul complet', command=self.start_desktop).pack(side='left', padx=8)
        ttk.Label(frame, text='Ctrl+click: mai multe ferestre. Pentru CLI nou: actualizează și selectează-l.', wraplength=690).pack(anchor='w', pady=6)
        self.code = tk.StringVar(value='—')
        ttk.Entry(frame, textvariable=self.code, state='readonly', font=('Consolas', 24), justify='center').pack(fill='x', pady=10)
        bar2 = ttk.Frame(frame)
        bar2.pack(fill='x')
        self.start_button = ttk.Button(bar2, text='Generează cod', command=self.start)
        self.start_button.pack(side='left')
        ttk.Button(bar2, text='Copiază codul', command=self.copy).pack(side='left', padx=8)
        ttk.Button(bar2, text='Oprește sesiunea', command=self.stop).pack(side='right')
        self.status = tk.StringVar(value='Pregătit · prototip experimental')
        ttk.Label(frame, textvariable=self.status, wraplength=690).pack(anchor='w', pady=12)
        ttk.Label(frame, text='Fără cursor remote suprapus. Modificările și ferestrele deschise rămân vizibile local.', wraplength=690).pack(anchor='w')
        if sys.platform == 'win32':
            from .windows import WindowsBackend
            self.backend = WindowsBackend()
        elif sys.platform == 'darwin':
            from .macos import MacBackend
            self.backend = MacBackend()
            self.status.set('Mac host experimental · activează Screen Recording și Accessibility')
        if self.backend:
            self.refresh()
        else:
            self.start_button.configure(state='disabled')
            self.status.set('Gazda este disponibilă doar pe Windows și macOS.')
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def refresh(self):
        if not self.backend:
            return
        try:
            selected = {self.rows[i]['id'] for i in self.list.curselection()}
            self.rows = self.backend.discover()
            self.list.delete(0, 'end')
            for i, row in enumerate(self.rows):
                self.list.insert('end', row['title'])
                if row['id'] in selected:
                    self.list.selection_set(i)
            if not selected and self.rows:
                self.list.selection_set(0)
        except Exception as exc:
            messagebox.showerror('PacketBridge', str(exc))

    def grant(self):
        if self.backend:
            try:
                ids = [self.rows[i]['id'] for i in self.list.curselection()]
                self.backend.grant(ids)
                self.status.set(f'{len(ids)} ferestre aprobate pentru partajare')
            except Exception as exc:
                messagebox.showerror('Partajare', str(exc))

    def start(self):
        if self.agent or not self.backend:
            return
        self.grant()
        if not self.backend.windows():
            messagebox.showinfo('PacketBridge', 'Deschide Packet Tracer și selectează cel puțin o fereastră.')
            return
        try:
            self.agent = Agent(self.url.get(), self.backend, self.events)
        except ValueError as exc:
            messagebox.showerror('Adresă', str(exc))
            return
        self.start_button.configure(state='disabled')
        self.status.set('Conectare la server…')
        self.agent.start()

    def start_desktop(self):
        if sys.platform != 'win32' or self.agent:
            return
        from .windows import DesktopBackend
        accepted = messagebox.askyesno(
            'Control global',
            'Atenție: participantul va vedea și controla întregul desktop, inclusiv alte aplicații. Continui?')
        if not accepted:
            return
        self.backend = DesktopBackend()
        self.rows = self.backend.discover()
        self.list.delete(0, 'end')
        self.list.insert(0, self.rows[0]['title'])
        self.list.selection_set(0)
        self.start()

    def start_packettracer_session(self):
        if sys.platform != 'win32' or self.agent or not self.backend:
            return
        # Include every currently visible Packet Tracer top-level window.
        # Newly opened windows can still be added with Refresh + Share selection.
        self.list.selection_set(0, 'end')
        if not self.list.curselection():
            messagebox.showinfo('PacketBridge', 'Deschide Packet Tracer înainte de partajare.')
            return
        if hasattr(self.backend, 'grant_all'):
            self.backend.grant_all()
        else:
            self.grant()
        self.start()

    def client(self):
        try:
            webbrowser.open(relay_url(self.url.get()))
        except ValueError as exc:
            messagebox.showerror('Adresă', str(exc))

    def copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.code.get())

    def stop(self):
        if self.agent:
            self.agent.stop.set()
            self.status.set('Se închide sesiunea…')
        self.code.set('—')

    def close(self):
        self.stop()
        self.root.destroy()

    def poll(self):
        try:
            while True:
                data = self.events.get_nowait()
                kind = data['type']
                if kind == 'code':
                    code = data['code']
                    self.code.set(code[:5] + '-' + code[5:])
                    self.status.set('Cod valabil 10 minute · aștept participantul')
                elif kind == 'request':
                    agent = self.agent
                    accepted = messagebox.askyesno('Cerere de conectare', 'Cineva care are codul solicită acces la ferestrele aprobate.\n\nAccepți sesiunea?')
                    if agent and not agent.stop.is_set():
                        agent.commands.put_nowait({'type': 'approve' if accepted else 'deny', 'request': data['request']})
                elif kind == 'connected':
                    self.code.set('CONECTAT')
                    self.status.set('Sesiune activă · Oprește sesiunea revocă accesul')
                elif kind == 'error':
                    self.status.set('Eroare: ' + data['message'])
                elif kind == 'closed':
                    self.agent = None
                    self.code.set('—')
                    self.start_button.configure(state='normal' if self.backend else 'disabled')
                    self.status.set(('' if not self.status.get().startswith('Eroare:') else self.status.get() + ' · ') + 'Sesiune închisă. Generează alt cod pentru reconectare.')
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
