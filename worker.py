from utils import *
from threading import Semaphore, Thread
from collections import deque
from itertools import chain
import random
import time
from collections.abc import Iterable

class GenericWorker(Thread):
    HAS_DELAY = False
    def __init__(self, typ, pid, pool, debug=None, ene=None):
        Thread.__init__(self, daemon=True)
        self.typ = typ
        self.pid = pid
        self.size = pool.size
        self.cx, self.cy, self.cz = pool.counts
        self.pool = pool
        self.debug: Debug = debug
        self.queue: deque = pool.queues[pid]
        self.msem = pool.msems[pid]
        self.state = ST.IDLE
        self.work_th = Thread(target=self.work, daemon=True)
        self.desc = "%d-%s" % (pid, typ.name)
        self.desc_long = "%d-%s-%02d" % (pid, typ.name, pool.id_in_group(pid))

        self.clock = 0
        self.pqus = {t: [] for t in pool.types}
        self.pqu = []
        self.sem = Semaphore(0)
        self.opp = PTyp.Y if self.typ==PTyp.X else (PTyp.X if self.typ==PTyp.Y else PTyp.NONE)
        self.copp, self.cown =  (self.cy, self.cx) if self.typ==PTyp.X else  (self.cx, self.cy)
        self.own_req = None
        self.ack_count = 0
        self.order = 0
        self.oppr = 0
        self.pair = -1
        self.last_crit = 0
        self.energy = ene if ene else self.cz
        self.energy_max = self.energy
        self.block = False
        self.has_delay = GenericWorker.HAS_DELAY
        self.max_delay = 0.1

        self.init2()


    def mpqu(self, m):
        return self.pqus[self.pool.typemap[m.sender]]

    def putqu(self, m, qu=None):
        if qu is None:
            qu = self.mpqu(m)
        #heapq.heappush(qu, (m.cl, m.sender))
        qu.append((m.cl, m.sender))
        qu.sort()

    def lpopqu(self, typ):
        if self.pqus[typ]:
            r, self.pqus[typ] = self.pqus[typ][0], self.pqus[typ][1:]
            return r
        return None
    
    def delqu(self, m):
        # print(self.pqus[self.opp], "-", m.sender)
        self.pqus[m.styp] = list(filter(lambda e: e[1] != m.sender, self.pqus[m.styp]))
        # print(self.pqus[self.opp])

    def log(self, *args, **kwargs):
        if self.debug:
            self.debug.log("[%4s %s]" % (self.desc, self.state_desc()), *args, f"@ {self.clock}", **kwargs)#, "\t\t\t", time.time(), **kwargs)

    def send(self, tid, mtyp, data={}, cl=None):
        self.clock += 1
        if cl is None:
            cl = self.clock
        m = TMsg(mtyp, self.pid, self.typ, data, cl)
        self.log(   ">%4s" % (self.pool.threads[tid].desc), 
                    m.typ.name,
                    f"[cl={m.cl}]",
                    m.data, 
                    lvl=30)

        
        self.pool.send(tid, m)
        

    def send_to_typ(self, typ, mtyp, **kwargs):
        for t in typ if isinstance(typ, Iterable) else [typ]:
            # cl = self.clock+1
            for tid in self.pool.get_of_type(t):
                if tid != self.pid:
                    if self.has_delay: time.sleep(random.random()*self.max_delay)
                    self.send(tid, mtyp, **kwargs)
                    

    def pdesc(self, pid):
        return self.pool.desc(pid)

    def state_desc(self):
        # return self.state.name[0]+"+"+str(self.energy)+"_"+str(self.ack_count)+">"+str(self.cown - self.energy)
        return f"{self.state.name[0]}E{self.energy}a{self.ack_count}"

    def _recv(self):
        self.msem.acquire()
        
        # time.sleep(0.2+random.random()*0.3)
        m = self.queue.popleft()

        self.log(   "<%4s" % (self.pdesc(m.sender)), 
                    m.typ.name,
                    f"[cl={m.cl}]",
                    m.data, 
                    lvl=20)

        if m.typ == MTyp.ACK:
            if self.has_delay: time.sleep(random.random()*self.max_delay)
        else:
            if self.has_delay: time.sleep(random.random()*self.max_delay)
        self.clock = max(self.clock, m.cl) + 1
        
        if m.typ == MTyp.TER:
            exit(0)
        return m
    
    def process_msg(self, m: TMsg):
        pass

    def message(self):
        self.log("/////MESSENGER/////", lvl=1)
        self.send_to_typ(PTyp.Z, MTyp.WAK)

    def dec(self):
        self.log("DEC", lvl=19)
        self.pool.dec()
        # if self.is_messenger:
        #     self.message()
        #     self.is_messenger = False
            
    def init2(self):
        self.dak_count = 0


    def standard_pairing(self, m: TMsg):
        if m.typ == MTyp.PAR:
            if self.pair == -1:# or m.sender == self.pair:
                self.pair = m.sender
                self.send(m.sender, MTyp.ACC)
            else:
                self.log(f"QU {m.sender}", lvl=21)
                self.putqu(m)
        elif m.typ == MTyp.FIN:
            if m.styp == self.opp:
                self.delqu(m)
                self.log(f"UNQU {m.sender}", lvl=21)
                if m.sender == self.pair and self.state == ST.WAIT:
                    nxt = self.lpopqu(self.opp)
                    if nxt:
                        tid = nxt[1]
                        self.pair = tid
                        self.send(tid, MTyp.ACC)
                    else:
                        self.pair = -1
                return True
            return False
        elif m.typ == MTyp.ACC:
            self.state = ST.PAIR
            self.sem.release()
        else:
            return False
        return True

    def send_req_if_ok(self, to_typ):
        # if self.energy > 0:
        # self.clock = (cl := self.clock+1)

        self.state = ST.DOOR
        cl = self.clock
        self.own_req = (cl, self.pid)
        self.ack_count = 0
        
        self.send_to_typ(to_typ, MTyp.REQ, cl=cl)
        
        self.try_enter()
        return True
        # return False

    def try_enter(self):
        
        if self.state == ST.DOOR and self.ack_count >= self.cown - self.energy and not self.block:
            self.state = ST.CRIT
            self.energy -= 1
            self.log("ENTER", lvl=9)
            self.log("DEC-------", lvl=5)
            self.dack_count = 0
            self.send_to_typ(self.typ, MTyp.DEC)
            self.release_typ(PTyp.X)

            self.sem.release()
            
            return True
        self.log("CANT ENTER+++++", self.state.name, self.block, lvl=11)
        return False

    def handle_req(self, m: TMsg):
        req = (m.cl, m.sender)
        should_qu = False
        if self.state == ST.DOOR and self.own_req < req:
            should_qu = True

        if should_qu:
            self.putqu(m)
        else:
            self.send(m.sender, MTyp.ACK)

    # def release_if_ok(self):
    #     while self.energy > 0:
    #         nxt = self.lpopqu(self.typ)
    #         if nxt is not None:
    #             tid = nxt[1]
    #             self.energy -= 1
    #             self.send(tid, MTyp.ACK)
    #         else:
    #             break
            
    def release_typ(self, typ):
        while True:
            nxt = self.lpopqu(typ)
            if not nxt:
                break
            tid = nxt[1]
            self.send(tid, MTyp.ACK)

    def try_pair(self):
        if self.pqus[self.opp]:
            tid = self.lpopqu(self.opp)[1]
            self.pair = tid
            self.send(tid, MTyp.ACC)
            return True
        return False

    # def work(self):
    #     to = random.randint(0, self.size-1)
    #     self.send(to, MTyp.REQ, {"pid": self.pid})
    #     time.sleep(2)
        # self.log("CRIT")
        # self.log(self.pqus[self.typ], "OWN", self.own_req)

    def run(self):
        self.work_th.start()
        while 1:
            m = self._recv()
            self.process_msg(m)