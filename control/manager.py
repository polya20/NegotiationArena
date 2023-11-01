import os
import time
from pathlib import Path
from typing import List
import logging
from log_dumper import LogDumper
from objects.utils import StateTracker
from agents.agents import Agent

class Manager:

    def __init__(self, 
                 agents: List[Agent],
                 n_rounds,
    ):
        self.agents = agents
        # initialize agent with empty state
        self.agents_state = [ [StateTracker(iteration=-1, 
                                            goals=agent.goals,
                                            resources=agent.resources[0])]  for agent in self.agents]
        self.n_rounds = n_rounds
        self.global_message_queue = []
        self.message_history = []
        logging_path = os.environ.get("NEGOTIATION_LOG_FOLDER")
        # start with agent 0
        self.turn = 0
        
        # initialize agents with init_prompt
        for agent in self.agents:
            agent.init_agent()
            

        # logging init 
        run_epoch_time_ms = round(time.time() * 1000)               
        print(logging_path)
        # create datastore path
        self.log_path = os.path.join(logging_path,str(run_epoch_time_ms))
        self.log_dumper = LogDumper(self.log_path)

        Path(self.log_path).mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            format='%(message)s',
            level=logging.INFO,
            filename=os.path.join(self.log_path,'interaction.log'),
            force=True
        )

        
    def negotiate(self):
        # negotiation over rounds
        for iteration in range(0, self.n_rounds*2):
            state_tracker = StateTracker()
            state_tracker.iteration = iteration
            state_tracker.goals = self.agents[self.turn].goals
            state_tracker.set_resources(self.agents[self.turn].resources[-1])

            print("Iteration: {}".format(iteration))
            logging.info("Iteration: {}".format(iteration))
            logging.info("Turn: Player {}\n".format(self.turn))
            
            # if there are messages in queue
            if self.global_message_queue:
                # extract messages from queue
                # assume for now only one message
                received_msg = self.global_message_queue.pop()
                self.message_history.append(received_msg)
                self.agents[self.turn].receive_messages(received_msg)
                # update state tracker
                # TODO: what about messages from MESSAGE?
                state_tracker.set_player_response(received_msg.data['player_response'])
                state_tracker.set_received_trade(received_msg.data['proposed_trade'])
                state_tracker.set_received_message(received_msg.data['message'])

            # update beliefs (usually if there is new message)
            self.agents[self.turn].update_beliefs()

            # make agent think about and make a trade
            message = self.agents[self.turn].make_trade()

            if message:
                self.global_message_queue.append(message)
                # update state tracker
                state_tracker.setattrs(**message.data)
                    
            # update agent state
            self.agents_state[self.turn].append(state_tracker)

            # logging
            logging.info("\nPlayer State: {}".format(state_tracker))
            for k,v in self.agents_state[self.turn][-1].__dict__.items():
                logging.info("{}:{}".format(k,str(v)))
            logging.info('=====\n')
        
            end = self.check_exit_condition(state_tracker.player_response, iteration)

            if end:
                return end
    
            # logic to update agent turn
            self.turn = 1 - self.turn

    def check_exit_condition(self, decision, iteration):
        """
        Extract agent beliefs at the end negotiation and check of goal is met
        """
        # IF ACCEPTED OR LAST ITERATION
        if decision == "ACCEPTED" or iteration == (self.n_rounds*2 - 1):
            for idx, agent in enumerate(self.agents):
                # kill agent
                agent.kill(decision)
                
                state_tracker = StateTracker()
                state_tracker.iteration = iteration + 1
                state_tracker.goals = agent.goals
                # get end state resources
                state_tracker.resources = agent.resources[-1]
                state_tracker.player_response = decision
                self.agents_state[idx].append(state_tracker)

                if agent.goals.goal_reached(agent.resources[-1]):
                    logging.info("Agent {} REACHED the goal!".format(idx))
                else:
                    logging.info("Agent {} DID NOT reach the goal!".format(idx))
                    
            self.log_dumper.dump_conversation(self.agents)
            self.log_dumper.dump_agent_state(self.agents_state)

            return True
        
        return False

    def __exit__(self):
        for idx, agent in enumerate(self.agents):
            agent.dump_conversation(os.path.join(self.log_path,"agent_{}.txt".format(idx)))

    def log(self):
        """
        Log conversation in human interpretable format
        """


class PromptManager:

    def __init__(self):
        pass

    def trade_formatter(self, opponent_proposal, opponent_decision):

        opponent_response = None

        # append opponent response from previous iteration
        if opponent_proposal or opponent_decision:
            if opponent_decision:
                opponent_response = "PLAYER RESPONSE : {}".format(opponent_decision) + "\n" + \
                                    "NEWLY PROPOSED TRADE : {}".format(opponent_proposal.to_prompt())
            else:
                opponent_response = "NEWLY PROPOSED TRADE : {}".format(opponent_proposal.to_prompt())

        return opponent_response