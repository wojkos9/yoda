import random
import time

from utils import *
from worker import GenericWorker
from pool import WorkerPool

from threading import Semaphore


class WorkerX(GenericWorker):
    def __init__(self, *args, **kwargs):
        GenericWorker.__init__(self, PTyp.X, *args, **kwargs)
        self.opp = PTyp.Y
        self.max_cl_letin = None
        self.sem2 = Semaphore(1)
        self.inc_count = 0

    def process_msg(self, m: TMsg):
        r = self.standard_pairing(m)
        if not r:
            if m.typ == MTyp.END:
                if self.state > ST.WAIT:
                    self.sem.release()
            elif m.typ == MTyp.REQ:
                if m.styp == self.typ:
                    self.handle_req(m)
                elif m.styp == PTyp.Z:
                    if self.state not in (ST.CRIT,):
                        # self.block = True
                        self.send(m.sender, MTyp.ACK)
                    else:
                        self.putqu(m)

            elif m.typ == MTyp.ACK:
                if m.cl > self.own_req[0]:
                    self.ack_count += 1
                    if self.ack_count==self.cx-1:
                        # if self.energy == 0:
                        #     self.message()
                        #     self.log("MESSACK", lvl=5)
                        self.sem2.release()
                    self.try_enter()
                

            elif m.typ == MTyp.INC:
                self.energy += 1

                self.inc_count += 1
                if self.inc_count == self.energy_max:
                    self.inc_count = 0
                    # if self.state == ST.BLOC:
                    #     self.state = ST.IDLE
                    #     self.release_typ(PTyp.X)
                    #     self.sem.release()
                    # elif self.state == ST.PAIR:
                    #     pass
                    self.block = False
                    self.try_enter()

            elif m.typ == MTyp.DEC:
                self.energy -= 1
                self.send(m.sender, MTyp.DAK)
                if self.energy == 0:
                    # if self.ack_count == self.cx-1:
                    #     self.is_messenger = True
                    #     self.log("MESSENE", lvl=5)
                    # self.send_to_typ(PTyp.Z, MTyp.WAK)
                    self.block = True
            elif m.typ == MTyp.DAK:
                self.dack_count += 1
                if self.dack_count == self.cx - 1:
                    if self.energy == 0:
                        self.message()
                    self.sem2.release()
    
    def work(self):
        self.pair = self.cown + self.pid
        while 1:
            self.pair = -1
            

            # last = self.state
            # self.state=ST.X
            # self.sem2.acquire()
            # self.state=last
            # self.ack_count = 0

            self.state = ST.WAIT
            
            self.try_pair()
            self.sem.acquire()
            self.state = ST.PAIR

            self.send_req_if_ok(self.typ)

            self.sem.acquire()
            self.state = ST.CRIT
            
            
            self.send(self.pair, MTyp.STA)
            self.last_crit += 1

            # time.sleep(1+random.random())

            
            self.send(self.pair, MTyp.END)
            
            self.sem.acquire()
            # self.pair = -1
            self.state = ST.IDLE
            self.dec()
            
            self.release_typ(PTyp.Z)
            
            self.sem2.acquire()

            # if self.energy == 0:
            #     self.state = ST.BLOC
                
            #     self.sem.acquire()
            #     self.state = ST.IDLE
            # time.sleep(1)
    
class WorkerY(GenericWorker):
    def __init__(self, *args, **kwargs):
        GenericWorker.__init__(self, PTyp.Y, *args, **kwargs)
        self.opp = PTyp.X
        self.par_cl = -1

    def process_msg(self, m: TMsg):
        if m.typ == MTyp.ACC:
            if self.state == ST.WAIT and m.cl > self.par_cl:
                self.send(m.sender, MTyp.ACC)
                self.pair = m.sender
                self.state = ST.PAIR
                self.sem.release()
            elif m.sender == self.pair and m.cl > self.par_cl:
                self.send(m.sender, MTyp.ACC)
        elif m.typ == MTyp.END:
            if self.state > ST.WAIT:
                self.sem.release()
        elif m.typ == MTyp.STA:
            self.sem.release()

        # elif m.typ == MTyp.PAR:
        #     if self.state == ST.WAIT:
        #         self.send(m.sender, MTyp.PAR)

    def work(self):
        # GenericWorker.work(self)
        self.pair = self.pid - self.cx
        while 1:
            self.pair = -1
            
            cl = self.clock
            self.par_cl = cl
            self.state = ST.WAIT
            self.send_to_typ(PTyp.X, MTyp.PAR, cl=cl)

            self.sem.acquire()
            self.state = ST.PAIR
            
            self.send_to_typ(self.opp, MTyp.FIN)
            self.state = ST.DOOR

            self.sem.acquire()
            self.state = ST.CRIT
            self.last_crit += 1

            # time.sleep(random.random())
            
            self.send(self.pair, MTyp.END)
            self.sem.acquire()
            # self.pair = -1
            self.state = ST.IDLE
            # time.sleep(1)

class WorkerZ(GenericWorker):
    def __init__(self, *args, **kwargs):
        GenericWorker.__init__(self, PTyp.Z, *args, **kwargs)

    def process_msg(self, m: TMsg):
        if m.typ == MTyp.WAK:
            self.log("WAKE")
            if self.state == ST.IDLE:
                self.state = ST.DOOR
                self.log("WAKE2")
                self.sem.release()
        elif m.typ == MTyp.ACK:
            self.ack_count += 1
            if self.ack_count == self.cx:
                self.state = ST.CRIT
                self.sem.release()

    def work(self):
        while 1:
            self.sem.acquire()

            self.ack_count = 0
            self.state = ST.DOOR
            self.send_to_typ(PTyp.X, MTyp.REQ)

            self.sem.acquire()
            self.state = ST.CRIT
            self.last_crit += 1
            # time.sleep(0.3*random.random())
            
            self.pool.energy += 1
            self.state = ST.IDLE
            
            self.log("INC+++++++", lvl=5)
            self.send_to_typ([PTyp.X], MTyp.INC)
            
            
if __name__=="__main__":
    dbg = Debug(0)
    GenericWorker.HAS_DELAY = False
    pool = WorkerPool((4, 4, 5), dbg,
                        classmap={PTyp.X: WorkerX, PTyp.Y: WorkerY, PTyp.Z: WorkerZ})

    pool.start()
    pool.rep_th()
    time.sleep(0.5)
    pool.join()