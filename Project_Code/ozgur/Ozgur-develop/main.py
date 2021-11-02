# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
# !/usr/bin/python

import sys
# from comsim import *
import math
import numpy as np
import matplotlib.pyplot as plt
from collections import OrderedDict
import json
import logging
from tqdm.auto import tqdm

import sys
import random
import queue
import collections
import math
import copy

if sys.version_info > (3,):
    import queue as queue
else:
    import Queue as queue


class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open("logfile.log", "a", encoding='utf-8')

    def log(self, header, text):
        lText = text.split('\n')
        lHeader = [header] + [''] * (len(lText) - 1)
        print('\n'.join(['{0:10} {1}'.format(h, t) \
                         for h, t in zip(lHeader, lText)]))

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        # this flush method is needed for python 3 compatibility.
        # this handles the flush command by doing nothing.
        # you might want to specify some extra behavior here.
        pass


sys.stdout = Logger()


class Message(object):

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return '[{0}]'.format(self.name)

    def getName(self):
        return self.name


class ProtocolMessage(Message):

    def __init__(self, message, length, content=None):
        Message.__init__(self, message)
        self.length = length
        self.content = content



    def __str__(self):
        return '<{0}>(L={1})'.format(self.getName(), self.length)

    def getLength(self):
        return self.length

    def fragment(self, lenPayload, lenFixed):
        fragments = []

        msgLen = self.getLength()
        while msgLen > 0:
            lenFrag = min(msgLen, lenPayload)
            msgLen -= lenFrag
            fragments.append(ProtocolMessage('{0}.f{1}'.format(
                self.getName(), len(fragments)), lenFrag + lenFixed))

        return fragments


class Scheduler(object):

    def __init__(self):
        self.reset()

    def empty(self):
        return self.queue.empty()

    def reset(self):
        self.time = 0.
        self.timeOncePerEvent = None
        self.queue = queue.PriorityQueue()

    def registerEventAbs(self, event, time, priority=0):
        if time < self.time:
            raise Exception('Cannot register event in past')
        self.queue.put((time, priority, event))
        return time

    def registerEventRel(self, event, time, priority=0):
        return self.registerEventAbs(event, self.time + time, priority)

    def getTime(self):
        return self.time

    def getTimeOncePerEvent(self):
        timeOncePerEvent = self.timeOncePerEvent
        self.timeOncePerEvent = None
        return timeOncePerEvent

    def done(self):
        return self.queue.empty()

    def runStep(self):
        """
        Run one single step
        """
        if self.queue.empty():
            # there is no event to process => just do nothing
            return self.time

        # retrieve the next event from the queue
        time, priority, event = self.queue.get()
        if time < self.time:
            raise Exception('Cannot handle event from past')

        # proceed current time to event time
        self.time = time
        self.timeOncePerEvent = time

        # execute the event
        event.execute()

        # return the new current time
        return self.time

    def run(self):
        while not self.done():  # original=100
            # print("time:"+str(self.time))
            self.runStep()


class Event(object):
    """
    This is the base class for scheduler events
    """

    def execute(self):
        pass


class Callback(Event):
    """
    This is the class representing a callback event for the scheduler
    """

    def __init__(self, callback, **pars):
        self.callback = callback
        self.pars = pars

    def execute(self):
        self.callback(**self.pars)

    def __lt__(self, other):
        return False


class LoggingClient(object):

    def __init__(self, logger):
        self.logger = logger

    def log(self, text):
        print(text)
        if not self.logger:
            return
        # Print the current only once for each registered event
        timeOncePerEvent = self.scheduler.getTimeOncePerEvent()
        if timeOncePerEvent is not None:
            # >>> First log line for current event >>>
            header = '[{0:>.3f}s]'.format(timeOncePerEvent)
        else:
            # >>> The was a log line for the same event before
            # Means same time as previous line
            header = '*'
        self.logger.log(header, '{0}: {1}'.format(self.getName(), text))


class Agent(LoggingClient):

    def __init__(self, name, scheduler, **params):
        LoggingClient.__init__(self, params.get('logger', None))
        self.name = name
        self.scheduler = scheduler
        self.medium = None

        medium = params.get('medium', None)
        if medium:
            medium.registerAgent(self)

    def getName(self):
        return self.name

    def registerMedium(self, medium):
        if self.medium:
            raise Exception('Agent "{0}" already registered with medium'.format(self.name))
        self.medium = medium

    def offerMedium(self, medium):
        return False

    def receive(self, message, sender):
        pass


class ProtocolAgent(Agent):

    def __init__(self, name, scheduler, **params):
        Agent.__init__(self, name, scheduler, **params)
        self.txQueue = collections.deque()
        self.txCount = 0
        self.rxCount = 0

    def getTxCount(self):
        return self.txCount

    def getRxCount(self):
        return self.rxCount

    def offerMedium(self, medium):

        if len(self.txQueue) > 0:

            # retrieve next message (and corresponding receiver) from TX queue
            message, receiver = self.txQueue.popleft()[:2]

            # track the number of bytes transmitted
            if isinstance(message, ProtocolMessage):
                self.txCount += message.getLength()

            # initiate message transmission
            medium.initiateMsgTX(message, self, receiver)

            # We took access to the medium
            return True

        else:

            # Don't need access to the medium
            return False

    # called by subclasses of ProtocolAgent
    def addMsgToTxQueue(self, message, receiver=None):

        self.log(f'Adding message <{format(message.getName())}> to transmission queue')

        # add message to transmission queue\

        self.txQueue.append((message, receiver, self.scheduler.getTime()))
        # detect message congestion
        if len(self.txQueue):
            times = [m[2] for m in self.txQueue]
            if (max(times) - min(times)) > 0.:
                self.log(TextFormatter.makeBoldYellow('Warning: Potential' + \
                                                      ' message congestion for {0} (N = {1}, d = {2:>.3f}s)' \
                                                      .format(self.name, len(self.txQueue),
                                                              max(times) - min(times))))

        # trigger medium access arbitration
        if self.medium is not None:
            self.medium.arbitrate()
        else:
            self.log('Warning: No medium available')

    # called by Medium class
    def receive(self, message, sender):
        # track the number of bytes received
        if isinstance(message, ProtocolMessage):
            self.rxCount += message.getLength()

        # sender is agent object instance
        self.log(TextFormatter.makeBoldGreen(
            '<-- received message {1} from {2}'.format(
                self.name, str(message), sender.getName())))


class GenericClientServerAgent(ProtocolAgent):

    def __init__(self, name, scheduler, flights, **kwparam):

        ProtocolAgent.__init__(self, name, scheduler, **kwparam)

        # the flight structure defining the communication sequence
        self.flights = flights

        # the retransmission timeout function
        self.timeouts = kwparam.get('timeouts', None)

        # communictation sequence complete callback
        self.onComplete = kwparam.get('onComplete', None)

        # reset
        self.reset()  # it causes "flights" to be unsegmintized ???

    def reset(self):

        # not yet done with the communication sequence
        self.done = False

        # Time taken to complete the communication sequence
        self.doneAtTime = None

        # the number of transmissions for each flight (one entry per flight)
        self.nTx = [0] * len(self.flights)

        # keep track of the number of times messages have been received
        self.nRx = [[0] * len(flight) for flight in self.flights]

        # keep track the out of order delivery for messages of that particular flight
        self.oOd = [[0] * len(flight) for flight in self.flights]

        # keep track of the index of expected message for out of order delivery detection in receive func
        self.expectedMesInd = 0

        # keep track of the times when a message has been received
        self.tRx = [[[] for i in range(len(flight))] for flight in self.flights]

        # additionally keep track of the messages received in the second-to-last flight
        if len(self.flights) > 1:
            # >>> there is more than one flight
            self.nRx_stl_flight = [False] * len(self.flights[-2])

        # prepare to transmit / receive first flight
        self.currentFlight = None
        self.gotoNextFlight()

    def getTimeout(self, index):
        if self.timeouts:
            return self.timeouts(index)
        else:
            # No further retransmissions
            return None

    def printStatistics(self):

        for i in range(len(self.flights)):
            if self.isTXFlight(i):
                print('\nFlight #{0}: ===>'.format(i + 1))
                for j in range(len(self.flights[i])):
                    print('> {0} ({1}x)'.format(
                        self.flights[i][j].getName(), self.nTx[i]))
            else:
                print('\nFlight #{0}: <==='.format(i + 1))
                for j in range(len(self.flights[i])):
                    tStr = ', '.join(['{0:.2f}s'.format(t) for t in self.tRx[i][j]])
                    print('> {0} ({1}x): {2}'.format(
                        self.flights[i][j].getName(), self.nRx[i][j], tStr))

    def gotoNextFlight(self):
        # move on to the next flight if this is not the last flight
        if self.currentFlight is None:
            self.currentFlight = 0
        elif (self.currentFlight + 1) < len(self.flights):
            self.currentFlight += 1
        else:
            return
        if self.isTXFlight(self.currentFlight):
            self.log(f'Ready to transmit flight #{format(self.currentFlight + 1)}')
        else:
            self.log(f'Ready to receive flight #{format(self.currentFlight + 1)}')


    def transmitACK(self, flight, ack):
        RTO = None
        strRTO = ''
        if (flight + 1) < len(self.flights):
            RTO = self.getTimeout(0)
            if RTO is not None:
                strRTO = ', RTO = {0:>.1f}s'.format(RTO)
                self.scheduler.registerEventRel(Callback(
                    self.checkFlight, flight=flight), RTO)

        self.addMsgToTxQueue(ack)

    def transmitFlight(self, flight):

        if not self.isTXFlight(flight):
            # >>> Somehow the flight that is asked to be transmitted
            # is a flight that the other side should send >>>
            raise Exception('Trying to transmit an invalid flight!')

        # don't trigger the retransmission of the last flight using timeout
        RTO = None
        strRTO = ''
        if (flight + 1) < len(self.flights):
            RTO = self.getTimeout(self.nTx[flight])
            if RTO is not None:
                strRTO = ', RTO = {0:>.1f}s'.format(RTO)
                self.scheduler.registerEventRel(Callback(
                    self.checkFlight, flight=flight), RTO)

        if self.nTx[flight] == 0:
            # >>> This is the first transmission intent of this flight >>>
            self.log(f'Transmitting flight #{format(flight + 1)}')
        else:
            # >>> This is a rentransmission of this flight >>>
            self.log(TextFormatter.makeRed(f'Retransmitting flight #{format(flight + 1)} '
                                           f'({format(TextFormatter.nth(self.nTx[flight]))}'
                                           f' retransmission{format(strRTO)})'))

        # Add messages of the flight to the transmission queue
        for msg in self.flights[flight]:
            self.addMsgToTxQueue(copy.deepcopy(msg))

        # remember that this flight has been (re)transmitted
        self.nTx[flight] += 1

        # clear reception tracking of second-to-last flight
        if len(self.flights) > 1 and (flight + 1) == len(self.flights):
            self.nRx_stl_flight = [False] * len(self.flights[-2])

        # is this flight transmitted for the first time ...
        # equivalently: if self.nTx[flight] == 0
        if flight == self.currentFlight:
            # >>> YES >>>
            # move on to the next flight if this is not the last flight
            self.gotoNextFlight()

    def checkFlight(self, flight):
        # the second-to-last flight has to be treated differently
        doRetransmit = False
        if len(self.flights) > 1 and (flight + 2) == len(self.flights):
            # retransmit if at least one message is missing
            doRetransmit = min(self.nRx[flight + 1]) == 0
        else:
            # retransmit if every message is missing
            doRetransmit = max(self.nRx[flight + 1]) == 0
        if doRetransmit:
            # retransmit
            self.transmitFlight(flight)

    def receive(self, message, sender):
        ProtocolAgent.receive(self, message, sender)
        expectedFlight = self.currentFlight
        if (self.currentFlight + 1) == len(self.flights) and self.isTXFlight(self.currentFlight):
            # >>> we are handling the last flight and are supposed to potentially
            # retransmit it upon receiving the previous flight once more >>>
            expectedFlight -= 1

        # the list of expected messages
        expectedMsgs = [msg.getName() for msg in self.flights[expectedFlight]]

        # detect unexpected messages
        if message.getName() not in expectedMsgs:
            # >>> We received an unexpected message

            # List all previous flights the received message might be from
            potentialFlights = [iFlight for iFlight in range(expectedFlight)
                                if message.getName() in [msg.getName()
                                                         for msg in self.flights[iFlight]]]

            if len(potentialFlights) == 0:
                # >>> Received unknown message >>>
                logStr = 'Received unknown message <{0}>.' \
                    .format(message.getName())
                # print(logStr)
            elif len(potentialFlights) == 1:
                # >>> Received message from an earlier flight
                logStr = 'Received message <{0}> from earlier flight #{1}.' \
                    .format(message.getName(), potentialFlights[0] + 1)
                # print(logStr)




            else:
                # >>> Received message from an earlier flight
                logStr = f'Received message <{format(message.getName())}' \
                         f'> from earlier flight (warning: multiple flights possible).'
                print(logStr)

            self.log(logStr + ' Expecting one of {0}'.format(
                ', '.join([f'<{format(msg)}>,' for msg in expectedMsgs])))

            # Just ignore it
            return

        approach = 2
        ####For Approach 2 or Approach #1###########
        self.expectedMesInd = 0
        print(f'self.nRx before this reception is {self.nRx[expectedFlight]}')
        if approach == 2:
            for i in range(len(self.nRx[expectedFlight])):
                if self.nRx[expectedFlight][i] == 0:
                    break
            self.expectedMesInd = i
        elif approach == 1:
            for i in range(len(self.nRx[expectedFlight])-1, -1, -1):
                if i == len(self.nRx[expectedFlight]) - 1:#analyze the last index in list seperately
                    if self.nRx[expectedFlight][i] >= 1:
                        self.expectedMesInd = -1
                        break
                else:
                    if self.nRx[expectedFlight][i] >= 1:
                        self.expectedMesInd = i+1
                        break
        print(f'Messages in order are:{expectedMsgs}')
        print(f'The expected Message Index before this reception for Approach #{approach} is {self.expectedMesInd}')







        # update reception tracker
        msgIndex = expectedMsgs.index(message.getName())
        self.nRx[expectedFlight][msgIndex] += 1
        self.oOd[expectedFlight][msgIndex] += 1
        self.tRx[expectedFlight][msgIndex] += [self.scheduler.getTime()]
        print(f'self.nRx after this reception is {self.nRx[expectedFlight]}')


        ACK = []
        ackIndex = []
        if msgIndex != self.expectedMesInd and self.expectedMesInd != -1:
            for i in range(len(self.flights[expectedFlight])):
                if self.nRx[expectedFlight][i] > 0:
                    ACK = ACK + [expectedMsgs[i]]
                    ackIndex = ackIndex + [i]
#                elif self.nRx[expectedFlight][i] == -1:
#                    ACK = ACK + [expectedMsgs[-1]]
        print(f'ACK :{ACK}\n msgIndex :{msgIndex} ---self.expectedMesInd :{self.expectedMesInd}')
        if ACK:
            ack_ProtocolMes = ProtocolMessage('ACK', 20, content=ackIndex)
            self.transmitACK(self.currentFlight, ack_ProtocolMes)

        # # register a callback for reception after <duration>
        # self.scheduler.registerEventRel(Callback(receiver.receive,
        #                                          message=message, sender=sender), duration,
        #                                 Medium.priorityReceive)
        # self.scheduler.registerEventRel(Callback(
        #     self.checkFlight, flight=flight), RTO)
#           def registerEventRel(self, event, time, priority=0):
            #self.scheduler.registerEventRel()
            # self.transmitFlight(self.currentFlight)


#            def registerEventRel(self, event, time, priority=0):
#                return self.registerEventAbs(event, self.time + time, priority)


        if message.getName == ACK:
            print(f'message Length is {message.getLength}')



        # keep track of receptions of second-to-last flight
        if len(self.flights) > 1 and (expectedFlight + 2) == len(self.flights):
            self.nRx_stl_flight[msgIndex] = True

        if (self.currentFlight + 1) < len(self.flights):
            # >>> we are NOT handling the last flight >>>
            # check whether flight has been received completely ...
            if min(self.nRx[self.currentFlight]) > 0:
                # >>> YES >>>
                self.log('Flight #{0} has been received completely'
                         .format(self.currentFlight + 1))
                # move on to the next flight
                self.gotoNextFlight()
                # transmit next flight
                self.transmitFlight(self.currentFlight)

            else:
                # >>> NO >>>
                missing = ', '.join(['<{0}>'.format(expectedMsgs[i])
                                     for i in range(len(expectedMsgs))
                                     if self.nRx[self.currentFlight][i] == 0])
                self.log(f'Messages still missing from flight #{self.currentFlight + 1}: {missing}')


        elif self.isTXFlight(self.currentFlight):
            # >>> we received a retransmission of the second-to-last flight
            # retransmit the last flight if we re-received the second-to-last flight completely
            if len(self.flights) > 1 and self.nRx_stl_flight.count(False) == 0:
                self.log(('The second-to-last flight (flight #{0}) has ' +
                          'been re-received completely').format(expectedFlight + 1))
                # do retransmission
                self.transmitFlight(self.currentFlight)

        # here: self.currentFlight == expectedFlight
        elif min(self.nRx[self.currentFlight]) > 0 and not self.done:
            # >>> we received the last flight completely
            self.log('Communication sequence completed at time {0:>.3f}s' \
                     .format(self.scheduler.getTime()))
            self.done = True

            self.doneAtTime = self.scheduler.getTime()
            print(self.doneAtTime)

            if self.onComplete:
                self.onComplete()


class GenericClientAgent(GenericClientServerAgent):

    def __init__(self, name, scheduler, flightStructure, **kwparam):
        GenericClientServerAgent.__init__(
            self, name, scheduler, flightStructure, **kwparam)

    def trigger(self):
        self.currentFlight = 0
        self.transmitFlight(self.currentFlight)

    def isTXFlight(self, flight):
        # Clients transmit even flight numbers (0, 2, ...)
        return (flight % 2) == 0

    # first message is sent
    # accoeding message lentgh duration message duration


class GenericServerAgent(GenericClientServerAgent):

    def __init__(self, name, scheduler, flightStructure, **kwparam):
        GenericClientServerAgent.__init__(
            self, name, scheduler, flightStructure, **kwparam)

    def isTXFlight(self, flight):
        # Server transmit odd flight numbers (1, 3, ...)
        return (flight % 2) == 1


class Medium(LoggingClient):
    priorityReceive = 0
    priorityUnblock = 1

    def __init__(self, scheduler, **params):
        LoggingClient.__init__(self, params.get('logger', None))
        self.scheduler = scheduler
        self.agents = {}
        self.sortedAgents = []
        self.blocked = False
        self.usage = {}
        self.name = params.get('name', 'Medium')

        # the data rate in bytes/second, None means 'unlimited'
        self.data_rate = params.get('data_rate', None)

        self.msg_slot_distance = params.get('msg_slot_distance', None)  # None means 'no slotting'
        self.msg_loss_rate = params.get('msg_loss_rate', 0.)
        self.bit_loss_rate = params.get('bit_loss_rate', 0.)
        self.inter_msg_time = params.get('inter_msg_time', 0.)

    def getName(self):
        return self.name

    def registerAgent(self, agent, priority=None):
        if agent.getName() in self.agents:
            print("......")
            raise Exception(f'Agent "{format(agent.getName())}" already registered')
        agent.registerMedium(self)
        self.agents[agent.getName()] = agent, priority
        self.sortAgents()

    def sortAgents(self):

        # sort agents with assigned priority
        agents = [(p, a) for a, p in self.agents.values() if p is not None]
        sortedAgents = list(map(lambda p, a: a, sorted(agents)))

        # append agents without assigned priority
        sortedAgents += [a for a, p in self.agents.values() if p is None]

        self.sortedAgents = sortedAgents

    def arbitrate(self):
        """
        Trigger the medium to check for pending messages
        in transmission queues of protocol agents
        """

        # No arbitration if medium is blocked
        if not self.blocked:
            # Offer the medium to each agent one by one
            # (using the list sorted by descending priority)
            for agent in self.sortedAgents:
                if agent.offerMedium(self):
                    # Stop once an agent has taken the medium
                    break

    def updateUsage(self, agent, duration):
        self.usage[agent.getName()] = float(duration) + \
                                      self.usage.get(agent.getName(), 0.)

    def getUsage(self, agent=None):
        if agent is None:
            return self.usage
        elif isinstance(agent, str):
            return self.usage.get(agent, 0.)
        elif isinstance(agent, Agent):
            return self.usage.get(agent.getName(), 0.)

    def blockMedium(self, agent, duration):
        self.updateUsage(agent, duration)
        self.block(duration)

    def block(self, duration):
        """
        Block the medium for a certain time given by <duration>
        """

        # Cannot block a blocked medium
        if self.blocked:
            raise Exception('Cannot block medium: medium is already blocked')
        self.blocked = True

        def unblock(medium):
            medium.blocked = False
            medium.arbitrate()

        # Use a callback to unblock the medium after <duration>
        self.scheduler.registerEventRel(Callback(
            unblock, medium=self), duration, Medium.priorityUnblock)

    def isBlocked(self):
        return self.blocked

    def getMsgLossProp(self, message):
        """
        Return the loss probability of a message. A message is considered lost
        if at least one of its bits is corrupt (probability affected by
        bit_loss_rate and the message's length) or if the whole message is lost
        (probability affected by msg_loss_rate).
        """
        if isinstance(message, ProtocolMessage):
            bit_corrupt_prop = \
                1. - (1. - self.bit_loss_rate) ** (message.getLength() * 8)
            return bit_corrupt_prop + self.msg_loss_rate \
                   - (bit_corrupt_prop * self.msg_loss_rate)
        else:
            return 0.

    def initiateMsgTX(self, message, sender, receiver=None):
        # make sender an agent object instance
        if isinstance(sender, str):
            sender, p_sender = self.agents[sender]

        if self.msg_slot_distance is not None:
            # determine time to next message slot
            frac, whole = math.modf(self.scheduler.getTime() / self.msg_slot_distance)
            timeToNextSlot = self.msg_slot_distance * (1. - frac)
        else:
            timeToNextSlot = 0.

        # Media constraints only apply to ProtocolMessages
        if not isinstance(message, ProtocolMessage):

            self.doMsgTX(message, sender, receiver)

        else:

            # duration of the transmission given by data_rate
            if self.data_rate is None:
                duration = 0.
            else:
                duration = float(message.getLength()) / float(self.data_rate)

            # block the medium
            self.block(timeToNextSlot + duration + self.inter_msg_time)

            self.updateUsage(sender, duration)

            # ... and register a callback to send message at the next slot
            event = Callback(self.doMsgTX, message=message, sender=sender, receiver=receiver, duration=duration)
            self.scheduler.registerEventRel(event, timeToNextSlot)

    def doMsgTX(self, message, sender, receiver, duration=None):

        # There is a message loss probability different
        # from zero only for ProtocolMessages
        if isinstance(message, ProtocolMessage):
            loss_prop = self.getMsgLossProp(message)
        else:
            loss_prop = None

        sender.log(TextFormatter.makeBoldBlue((f'--> sending message {format(str(message))} ' +
                                               f'(pl = {format(loss_prop * 100)})')))

        if not receiver:
            # this is a broadcast (let sender not receive its own message)
            for agent, p_receiver in filter(
                    lambda a: a[0] != sender, list(self.agents.values())):
                self.dispatchMsg(message, sender, agent, loss_prop, duration)
        else:
            # make receiver an object instance
            if isinstance(receiver, str):
                receiver, priority = self.agents[receiver]
            self.dispatchMsg(message, sender, receiver, loss_prop, duration)

    def dispatchMsg(self, message, sender, receiver, loss_prop, duration):

        # ozgur = self.agents.get(receiver.getName())[0]  # global receiver agent
        # if sender.nTx[sender.currentFlight - 1] != sender.detectRT[sender.currentFlight - 1]:
        #     receiver.oOd[receiver.currentFlight] = [0] * len(receiver.oOd[receiver.currentFlight])
        #     sender.detectRT[sender.currentFlight - 1] = sender.nTx[sender.currentFlight - 1]

        # handle random message loss according to loss_prop
        if loss_prop is None or random.random() >= loss_prop:
            # >>> message did not get lost >>>
            if duration is None:
                # immediate reception
                receiver.receive(message, sender)
            else:
                # register a callback for reception after <duration>
                self.scheduler.registerEventRel(Callback(receiver.receive,
                                                         message=message, sender=sender), duration,
                                                Medium.priorityReceive)
                print(self.agents.get(receiver.getName())[0].oOd)
        # Show lost messages only for normal receivers
        elif not receiver.getName().startswith('.'):
            self.log(TextFormatter.makeBoldRed(
                f'Lost message <{format(message.getName())}> sent from '
                f'{format(sender.getName())} to {format(receiver.getName())}'))



class TextFormatter(object):
    useColor = True

    strColorEnd = '\033[0m'

    @staticmethod
    def makeBoldWhite(s):
        if TextFormatter.useColor:
            return '\033[1m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeBoldRed(s):
        if TextFormatter.useColor:
            return '\033[1;31m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeBoldGreen(s):
        if TextFormatter.useColor:
            return '\033[1;32m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeBoldYellow(s):
        if TextFormatter.useColor:
            return '\033[1;33m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeBoldBlue(s):
        if TextFormatter.useColor:
            return '\033[1;34m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeBoldPurple(s):
        if TextFormatter.useColor:
            return '\033[1;35m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeBoldCyan(s):
        if TextFormatter.useColor:
            return '\033[1;36m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeGreen(s):
        if TextFormatter.useColor:
            return '\033[32m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeRed(s):
        if TextFormatter.useColor:
            return '\033[31m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def makeBlue(s):
        if TextFormatter.useColor:
            return '\033[34m' + s + TextFormatter.strColorEnd
        return s

    @staticmethod
    def indent(str, level=1):
        lines = [' ' * (4 if s else 0) * level + s for s in str.split('\n')]
        return '\n'.join(lines)

    @staticmethod
    def nth(number):
        if number == 1:
            return '1st'
        elif number == 2:
            return '2nd'
        elif number == 3:
            return '3rd'
        else:
            return '{0}th'.format(number)


def printFlights(flights):
    for i, flight in enumerate(flights):

        for message in flight:

            if (i % 2) == 0:
                print('{:>30} ---> {:30}'.format(message.getName(), ''))
            else:
                print('{:>30} <--- {:30}'.format('', message.getName()))


def segmentsize(flights, maxLenPayload, lenHeader):
    segmentedFlights = []
    residual = []
    for flight in flights:
        for msg in flight:
            payloadLen = msg.getLength() - lenHeader
            segmented = False
            # Add to-be-acked segments
            iSeg = 0
            while payloadLen >= maxLenPayload:
                segName = '{}.seg{}'.format(msg.getName(), iSeg)
                segPayloadLen = min(payloadLen, maxLenPayload)
                residual.append(ProtocolMessage(segName, segPayloadLen + lenHeader))
                segmentedFlights.append(residual)
                residual = []
                segmentedFlights.append([ProtocolMessage("ACK.{}".format(segName), 5 + lenHeader)])
                payloadLen -= segPayloadLen
                iSeg += 1
                segmented = True
                # Add un-acked (residual) message
            if payloadLen > 0:
                if segmented:
                    msgName = '{}.last'.format(msg.getName())
                else:
                    msgName = msg.getName()
                residual.append(ProtocolMessage(msgName, payloadLen + lenHeader))
        segmentedFlights.append(residual)
        residual = []
    #    print segmentedFlights
    return segmentedFlights


def Superfluous_Data(flights, ClientData, ServerData):
    tempdict = {}
    # List of all message lengths
    msgLength_list = []

    for elements in flights:
        for values in elements:
            msgLength_list.append(values.getLength())

    # print msgLength_list

    # Client message reception frequency
    clientdata_frequency = []
    for elements in ClientData:
        for values in elements:
            clientdata_frequency.append(values)

    # Server message reception frequency
    serverdata_frequency = []
    for elements in ServerData:
        for values in elements:
            serverdata_frequency.append(values)

    #    print 'Client Data---',clientdata_frequency
    #    print 'Server Data---',serverdata_frequency

    # If a message is transmitted more than once, it's Superfluous
    #    superfluousData_frequency= [x+y-1 for x,y in zip(clientdata_frequency, \
    #            serverdata_frequency)]
    Client_superfluousData_frequency = [x - 1 if x > 0 else x for x in clientdata_frequency]
    Server_superfluousData_frequency = [x - 1 if x > 0 else x for x in serverdata_frequency]

    tempdict['Total_superfluousData_frequency'] = map(sum, zip(Client_superfluousData_frequency,
                                                               Server_superfluousData_frequency))

    superfluousData_list = [x * y for x, y in zip(tempdict['Total_superfluousData_frequency'], \
                                                  msgLength_list)]
    # client_superfluouslist=[superfluousData_list[0],superfluousData_list[6],superfluousData_list[7],superfluousData_list[8],superfluousData_list[9],superfluousData_list[10]]
    # server_superfluouslist=[superfluousData_list[1],superfluousData_list[2],superfluousData_list[3],superfluousData_list[4],superfluousData_list[5],superfluousData_list[11],superfluousData_list[12]]
    # print superfluousData_list
    # print client_superfluouslist
    # print server_superfluouslist

    #    print 'Total Freq----',Total_superfluousData_frequency
    #    print 'Total---------',superfluousData_list
    tempdict['SuperFluous_data'] = sum(superfluousData_list)
    # tempdict['Client_Data']=sum(client_superfluouslist)
    # tempdict['Server_Data']=sum(server_superfluouslist)

    return tempdict


def Handshake(flights, listOfTimes, RetransmissionCriteria='exponential', LossRate=9e-3, datarate=500):
    tempDict = {}

    # logger = Logger()
    logger = None

    scheduler = Scheduler()

    if RetransmissionCriteria == 'exponential':
        timeouts = lambda i: 1 * (2 ** (i - 1))
    #        timeouts = lambda i: 1*2**i
    elif RetransmissionCriteria == 'linear':
        timeouts = lambda i: 1 * i
    elif RetransmissionCriteria == 'constant':
        timeouts = lambda i: 1
    else:
        # No retransmission at all
        timeouts = None

    server = GenericServerAgent(name='server1', scheduler=scheduler, flightStructure=flights, timeouts=timeouts,
                                logger=logger)
    client = GenericClientAgent(name='client1', scheduler=scheduler, flightStructure=flights, timeouts=timeouts,
                                logger=logger)

    medium = Medium(scheduler, data_rate=datarate / 8, bit_loss_rate=LossRate, inter_msg_time=0.001, logger=logger)
    medium.registerAgent(server)
    medium.registerAgent(client)
    client.trigger()

    scheduler.run()

    # Last flight can be received at either Client or Server side
    if len(flights) % 2 == 0:
        print(len(flights))
        handshaketime = client.doneAtTime
        print("handshaketime Client", client.doneAtTime)
    else:
        handshaketime = server.doneAtTime
        print("handshaketime Server", client.doneAtTime)

    # if hanshake was incomplete, don't append 'None' in the list
    if handshaketime != None:
        listOfTimes.append(handshaketime)

    tempDict['HS-Time'] = handshaketime
    tempDict['Total-Data'] = client.txCount + server.txCount
    # tempDict['Server-Data']=server.txCount
    # tempDict['Client-Data']=client.txCount
    Superfluous_Dict = Superfluous_Data(flights, client.nRx, server.nRx)
    tempDict['Superfluous_Messages_List'] = Superfluous_Dict['Total_superfluousData_frequency']
    tempDict['SFData'] = Superfluous_Dict['SuperFluous_data']

    tempDict['Retransmissions List'] = [x - 1 if x > 0 else x for x in
                                        map(sum, zip([y for y in client.nTx], [z for z in server.nTx]))]
    tempDict['Total flight Retransmissions'] = sum(
        [x - 1 if x > 0 else x for x in map(sum, zip([y for y in client.nTx], [z for z in server.nTx]))])
    # print("handshake Time", handshaketime);
    return tempDict


##################################main code lines###############################
n = 100

flights = [
    [
        ProtocolMessage('ClientHello', 87)
    ],

    [
        ProtocolMessage('ServerHello', 107),
        ProtocolMessage('Certificate', 800),
        ProtocolMessage('ServerKeyExchange', 165),
        ProtocolMessage('CertificateRequest', 71),
        ProtocolMessage('ServerHelloDone', 25)
    ],

    [
        ProtocolMessage('Certificate', 800),
        ProtocolMessage('ClientKeyExchange', 91),
        ProtocolMessage('CertificateVerify', 97),
        ProtocolMessage('ChangeCipherSpec', 13),
        ProtocolMessage('Finished', 37)
    ],

    [
        ProtocolMessage('ChangeCipherSpec', 13),
        ProtocolMessage('Finished', 37)
    ]
]

print("\nUnsegmentized")
printFlights(flights)
# message Header is taken 25, so message lengths should gradually bigger then 25
flights_msg_size = [60, 60]
Avg_hslist = []
std_hslist = []
HSlist = []
HandshakeList = []

segSize = 20
BER = 3 * 1E-4

data = {}

segmentizedHandshake = segmentsize(flights, segSize, 25)  # 25 is the Header size for each msg
print("\nSegmentized")
printFlights(segmentizedHandshake)

if BER not in data:
    data[BER] = {}

HSlist = []

for iteration in range(2):
    print(f'\nIteration {iteration} with segment size {segSize} and BER {BER} ')
    HSTime = Handshake(flights, HandshakeList, RetransmissionCriteria='linear', LossRate=BER,
                       datarate=10e3)

    HSduration = HSTime['HS-Time']
    print("HSduration:" + str(HSduration))
    HSlist.append(HSduration)
    # print(HSlist)
    print("Finished")

    mean = np.mean(HSlist)
    std = np.std(HSlist)

    data[BER][segSize] = (mean, std)
