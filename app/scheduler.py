# V2: o scheduler embutido foi substituído pelo serviço dedicado app.worker.
# Este arquivo fica apenas para compatibilidade com instalações antigas.
def start_scheduler():
    return None

class _Scheduler:
    running = False
    def shutdown(self, wait=False):
        return None

scheduler = _Scheduler()
