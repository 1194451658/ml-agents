# # Unity ML-Agents Toolkit
# ## ML-Agent Learning (PPO)
# Contains an implementation of PPO as described in: https://arxiv.org/abs/1707.06347

import logging
from collections import deque, defaultdict

import numpy as np
import tensorflow as tf

from mlagents.envs import AllBrainInfo, BrainInfo
from mlagents.trainers.buffer import Buffer
from mlagents.trainers.sac.policy import SACPolicy
from mlagents.trainers.trainer import Trainer, UnityTrainerException


logger = logging.getLogger("mlagents.trainers")


class SACTrainer(Trainer):
    """The PPOTrainer is an implementation of the PPO algorithm."""

    def __init__(
        self, brain, reward_buff_cap, trainer_parameters, training, load, seed, run_id
    ):
        """
        Responsible for collecting experiences and training PPO model.
        :param trainer_parameters: The parameters for the trainer (dictionary).
        :param training: Whether the trainer is set for training.
        :param load: Whether the model should be loaded.
        :param seed: The seed the model will be initialized with
        :param run_id: The The identifier of the current run
        """
        super(SACTrainer, self).__init__(brain, trainer_parameters, training, run_id)
        self.param_keys = [
            "batch_size",
            "buffer_size",
            "buffer_init_steps",
            "hidden_units",
            "learning_rate",
            "init_entcoef",
            "max_steps",
            "normalize",
            "num_epoch",
            "num_layers",
            "time_horizon",
            "sequence_length",
            "summary_freq",
            "target_update_steps",
            "tau",
            "use_recurrent",
            "summary_path",
            "memory_size",
            "model_path",
            "reward_signals",
        ]

        self.check_param_keys()
        self.check_demo_keys(trainer_parameters)

        self.step = 0
        self.train_interval = (
            trainer_parameters["train_interval"]
            if "train_interval" in trainer_parameters
            else 1
        )
        self.target_update_interval = trainer_parameters["target_update_steps"]
        self.policy = SACPolicy(seed, brain, trainer_parameters, self.is_training, load)

        stats = defaultdict(list)

        # collected_rewards is a dictionary from name of reward signal to a dictionary of agent_id to cumulative reward
        # used for reporting only
        self.collected_rewards = {"environment": {}}
        for _reward_signal in trainer_parameters["reward_signals"].keys():
            self.collected_rewards[_reward_signal] = {}

        self.stats = stats

        self.training_buffer = Buffer()

        self._reward_buffer = deque(maxlen=reward_buff_cap)
        self.episode_steps = {}

    def __str__(self):
        return """Hyperparameters for the SAC Trainer of brain {0}: \n{1}""".format(
            self.brain_name,
            "\n".join(
                [
                    "\t{0}:\t{1}".format(x, self.trainer_parameters[x])
                    for x in self.param_keys
                ]
            ),
        )

    @property
    def parameters(self):
        """
        Returns the trainer parameters of the trainer.
        """
        return self.trainer_parameters

    @property
    def get_max_steps(self):
        """
        Returns the maximum number of steps. Is used to know when the trainer should be stopped.
        :return: The maximum number of steps of the trainer
        """
        return float(self.trainer_parameters["max_steps"])

    @property
    def get_step(self):
        """
        Returns the number of steps the trainer has performed
        :return: the step count of the trainer
        """
        return self.step

    @property
    def reward_buffer(self):
        """
        Returns the reward buffer. The reward buffer contains the cumulative
        rewards of the most recent episodes completed by agents using this
        trainer.
        :return: the reward buffer.
        """
        return self._reward_buffer

    def check_demo_keys(self, trainer_parameters: dict):
        """
        Checks if the demonstration-aided parameters are set properly. 
        :param trainer_parameters: The hyperparameter dictionary passed to the trainer.
        """
        if "demo_aided" in trainer_parameters:
            if (
                "demo_path" not in trainer_parameters["demo_aided"]
                or "demo_strength" not in trainer_parameters["demo_aided"]
                or "demo_steps" not in trainer_parameters["demo_aided"]
            ):
                raise UnityTrainerException(
                    "demo_aided was specified but either demo_path, demo_strength, or demo_steps was not given."
                )

    def increment_step_and_update_last_reward(self):
        """
        Increment the step count of the trainer and Updates the last reward
        """
        if len(self.stats["Environment/Cumulative Reward"]) > 0:
            mean_reward = np.mean(self.stats["Environment/Cumulative Reward"])
            self.policy.update_reward(mean_reward)
        self.policy.increment_step()
        self.step = self.policy.get_current_step()

    def construct_curr_info(self, next_info: BrainInfo) -> BrainInfo:
        """
        Constructs a BrainInfo which contains the most recent previous experiences for all agents
        which correspond to the agents in a provided next_info.
        :BrainInfo next_info: A t+1 BrainInfo.
        :return: curr_info: Reconstructed BrainInfo to match agents of next_info.
        """
        visual_observations = []
        vector_observations = []
        text_observations = []
        memories = []
        rewards = []
        local_dones = []
        max_reacheds = []
        agents = []
        prev_vector_actions = []
        prev_text_actions = []
        action_masks = []
        for agent_id in next_info.agents:
            agent_brain_info = self.training_buffer[agent_id].last_brain_info
            if agent_brain_info is None:
                agent_brain_info = next_info
            agent_index = agent_brain_info.agents.index(agent_id)
            for i in range(len(next_info.visual_observations)):
                visual_observations[i].append(
                    agent_brain_info.visual_observations[i][agent_index]
                )
            vector_observations.append(
                agent_brain_info.vector_observations[agent_index]
            )
            text_observations.append(agent_brain_info.text_observations[agent_index])
            if self.policy.use_recurrent:
                if len(agent_brain_info.memories) > 0:
                    memories.append(agent_brain_info.memories[agent_index])
                else:
                    memories.append(self.policy.make_empty_memory(1))
            rewards.append(agent_brain_info.rewards[agent_index])
            local_dones.append(agent_brain_info.local_done[agent_index])
            max_reacheds.append(agent_brain_info.max_reached[agent_index])
            agents.append(agent_brain_info.agents[agent_index])
            prev_vector_actions.append(
                agent_brain_info.previous_vector_actions[agent_index]
            )
            prev_text_actions.append(
                agent_brain_info.previous_text_actions[agent_index]
            )
            action_masks.append(agent_brain_info.action_masks[agent_index])
        if self.policy.use_recurrent:
            memories = np.vstack(memories)
        curr_info = BrainInfo(
            visual_observations,
            vector_observations,
            text_observations,
            memories,
            rewards,
            agents,
            local_dones,
            prev_vector_actions,
            prev_text_actions,
            max_reacheds,
            action_masks,
        )
        return curr_info

    def add_experiences(
        self,
        curr_all_info: AllBrainInfo,
        next_all_info: AllBrainInfo,
        take_action_outputs,
    ):
        """
        Adds experiences to each agent's experience history.
        :param curr_all_info: Dictionary of all current brains and corresponding BrainInfo.
        :param next_all_info: Dictionary of all current brains and corresponding BrainInfo.
        :param take_action_outputs: The outputs of the Policy's get_action method.
        """
        self.trainer_metrics.start_experience_collection_timer()
        if take_action_outputs:
            self.stats["Policy/Entropy"].append(take_action_outputs["entropy"].mean())
            self.stats["Policy/Learning Rate"].append(
                take_action_outputs["learning_rate"]
            )
            for name, signal in self.policy.reward_signals.items():
                if signal.value_name in self.stats:
                    self.stats[signal.value_name].append(take_action_outputs["value"])

        curr_info = curr_all_info[self.brain_name]
        next_info = next_all_info[self.brain_name]

        for agent_id in curr_info.agents:
            self.training_buffer[agent_id].last_brain_info = curr_info
            self.training_buffer[
                agent_id
            ].last_take_action_outputs = take_action_outputs

        if curr_info.agents != next_info.agents:
            curr_to_use = self.construct_curr_info(next_info)
        else:
            curr_to_use = curr_info

        tmp_rewards_dict = {}
        for name, signal in self.policy.reward_signals.items():
            tmp_rewards_dict[name] = signal.evaluate(curr_to_use, next_info)

        for agent_id in next_info.agents:
            stored_info = self.training_buffer[agent_id].last_brain_info
            stored_take_action_outputs = self.training_buffer[
                agent_id
            ].last_take_action_outputs
            if stored_info is not None:
                idx = stored_info.agents.index(agent_id)
                next_idx = next_info.agents.index(agent_id)
                assert idx == next_idx
                if not stored_info.local_done[idx]:
                    for i, _ in enumerate(stored_info.visual_observations):
                        self.training_buffer[agent_id]["visual_obs%d" % i].append(
                            stored_info.visual_observations[i][idx]
                        )
                        self.training_buffer[agent_id]["next_visual_obs%d" % i].append(
                            next_info.visual_observations[i][next_idx]
                        )
                    if self.policy.use_vec_obs:
                        self.training_buffer[agent_id]["vector_obs"].append(
                            stored_info.vector_observations[idx]
                        )
                        self.training_buffer[agent_id]["next_vector_in"].append(
                            next_info.vector_observations[next_idx]
                        )
                    if self.policy.use_recurrent:
                        if stored_info.memories.shape[1] == 0:
                            stored_info.memories = np.zeros(
                                (len(stored_info.agents), self.policy.m_size)
                            )
                        self.training_buffer[agent_id]["memory"].append(
                            stored_info.memories[idx]
                        )
                    actions = stored_take_action_outputs["action"]
                    if self.policy.use_continuous_act:
                        pass
                        # actions_pre = stored_take_action_outputs["pre_action"]
                        # self.training_buffer[agent_id]["actions_pre"].append(
                        #     actions_pre[idx]
                        # )
                        # epsilons = stored_take_action_outputs["random_normal_epsilon"]
                        # self.training_buffer[agent_id]["random_normal_epsilon"].append(
                        #     epsilons[idx]
                        # )
                    else:
                        self.training_buffer[agent_id]["action_mask"].append(
                            stored_info.action_masks[idx]
                        )
                    a_dist = stored_take_action_outputs["log_probs"]
                    # value is a dictionary from name of reward to value estimate of the value head
                    value = stored_take_action_outputs["value"]
                    self.training_buffer[agent_id]["actions"].append(actions[idx])
                    self.training_buffer[agent_id]["prev_action"].append(
                        stored_info.previous_vector_actions[idx]
                    )
                    self.training_buffer[agent_id]["masks"].append(1.0)
                    self.training_buffer[agent_id]["done"].append(
                        next_info.local_done[idx]
                    )

                    for name, reward in tmp_rewards_dict.items():
                        # 0 because we use the scaled reward to train the agent
                        self.training_buffer[agent_id][
                            "{}_rewards".format(name)
                        ].append(tmp_rewards_dict[name][0][next_idx])
                        self.training_buffer[agent_id][
                            "{}_value_estimates".format(name)
                        ].append(value)

                    self.training_buffer[agent_id]["action_probs"].append(a_dist[idx])

                    for idx, (name, rewards) in enumerate(
                        self.collected_rewards.items()
                    ):
                        if agent_id not in rewards:
                            rewards[agent_id] = 0
                        if name == "environment":
                            # Report the reward from the environment
                            rewards[agent_id] += np.array(next_info.rewards)[next_idx]
                        else:
                            # Report the reward signals
                            rewards[agent_id] += tmp_rewards_dict[name][0][next_idx]


                if not next_info.local_done[next_idx]:
                    if agent_id not in self.episode_steps:
                        self.episode_steps[agent_id] = 0
                    self.episode_steps[agent_id] += 1
        self.trainer_metrics.end_experience_collection_timer()

    def process_experiences(self, current_info: AllBrainInfo, new_info: AllBrainInfo):
        """
        Checks agent histories for processing condition, and processes them as necessary.
        Processing involves calculating value and advantage targets for model updating step.
        :param current_info: Dictionary of all current brains and corresponding BrainInfo.
        :param new_info: Dictionary of all next brains and corresponding BrainInfo.
        """
        info = new_info[self.brain_name]
        for l in range(len(info.agents)):
            agent_actions = self.training_buffer[info.agents[l]]["actions"]
            if (
                info.local_done[l]
                or len(agent_actions) > self.trainer_parameters["time_horizon"]
            ) and len(agent_actions) > 0:
                agent_id = info.agents[l]
                # value_next = self.policy.get_value_estimates(bootstrapping_info, idx)
                # if info.local_done[l] and not info.max_reached[l]:
                #     value_next = 0.0
                # tmp_advantages = []
                # tmp_returns = []
                # for idx, name in enumerate(self.policy.reward_signals.keys()):
                #     bootstrap_value = value_next

                #     local_rewards = self.training_buffer[agent_id][
                #             '{}_rewards'.format(name)].get_batch()
                #     local_value_estimates = self.training_buffer[agent_id][
                #             '{}_value_estimates'.format(name)].get_batch()
                # local_return = get_discounted_returns(
                #     rewards=local_rewards,
                #     gamma=self.gamma_parameters[name],
                #     lambd=self.trainer_parameters['lambd'])
                # # This is later use as target for the different value estimates
                # self.training_buffer[agent_id]['{}_returns'.format(name)].set(local_return)
                # # self.training_buffer[agent_id]['{}_advantage'.format(name)].set(local_advantage)
                # tmp_returns.append(local_return)

                # global_returns = list(np.mean(np.array(tmp_returns), axis=0))
                # self.training_buffer[agent_id]['discounted_returns'].set(global_returns)

                self.training_buffer.append_update_buffer(
                    agent_id,
                    batch_size=None,
                    training_length=self.policy.sequence_length,
                )

                self.training_buffer[agent_id].reset_agent()
                if info.local_done[l]:
                    self.stats["Environment/Episode Length"].append(
                        self.episode_steps.get(agent_id, 0)
                    )
                    self.episode_steps[agent_id] = 0
                    for name, rewards in self.collected_rewards.items():
                        if name == "environment":
                            self.cumulative_returns_since_policy_update.append(
                                rewards.get(agent_id, 0)
                            )
                            self.stats["Environment/Cumulative Reward"].append(
                                rewards.get(agent_id, 0)
                            )
                            rewards[agent_id] = 0
                            self.reward_buffer.appendleft(rewards.get(agent_id, 0))
                        else:
                            self.stats[
                                self.policy.reward_signals[name].stat_name
                            ].append(rewards.get(agent_id, 0))
                            rewards[agent_id] = 0

    def end_episode(self):
        """
        A signal that the Episode has ended. The buffer must be reset.
        Get only called when the academy resets.
        """
        self.training_buffer.reset_local_buffers()
        for agent_id in self.episode_steps:
            self.episode_steps[agent_id] = 0
        for rewards in self.collected_rewards.values():
            for agent_id in rewards:
                rewards[agent_id] = 0

    def is_ready_update(self):
        """
        Returns whether or not the trainer has enough elements to run update model
        :return: A boolean corresponding to whether or not update_model() can be run
        """
        return (
            len(self.training_buffer.update_buffer["actions"])
            >= self.trainer_parameters["batch_size"]
            and self.step % self.train_interval == 0
            and self.step >= self.trainer_parameters["buffer_init_steps"]
        )

    def update_policy(self):
        """
        Uses demonstration_buffer to update the policy.
        The reward signal generators must be updated in this method at their own pace.
        """
        self.trainer_metrics.start_policy_update_timer(
            number_experiences=len(self.training_buffer.update_buffer["actions"]),
            mean_return=float(np.mean(self.cumulative_returns_since_policy_update)),
        )
        n_sequences = max(
            int(self.trainer_parameters["batch_size"] / self.policy.sequence_length), 1
        )
        value_total, policy_total, forward_total, inverse_total, entcoeff_total, q1loss_total, q2loss_total = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
        num_epoch = self.trainer_parameters["num_epoch"]
        for _ in range(num_epoch):
            buffer = self.training_buffer.update_buffer
            if (
                len(self.training_buffer.update_buffer["actions"])
                >= self.trainer_parameters["batch_size"]
            ):
                sampled_minibatch = buffer.sample_mini_batch(
                    self.trainer_parameters["batch_size"]
                )
                run_out = self.policy.update(
                    sampled_minibatch,
                    n_sequences,
                    update_target=self.step % self.target_update_interval == 0,
                )
                value_total.append(run_out["value_loss"])
                policy_total.append(run_out["policy_loss"])
                q1loss_total.append(run_out["q1_loss"])
                q2loss_total.append(run_out["q2_loss"])
                entcoeff_total.append(run_out["entropy_coef"])
        # Truncate update buffer if neccessary. Truncate more than we need to to avoid truncating
        # a large buffer at each update.
        if (
            len(self.training_buffer.update_buffer["actions"])
            > self.trainer_parameters["buffer_size"]
        ):
            self.training_buffer.truncate_update_buffer(
                int(self.trainer_parameters["buffer_size"] * 0.8)
            )

        self.stats["Losses/Value Loss"].append(np.mean(value_total))
        self.stats["Losses/Policy Loss"].append(np.mean(policy_total))
        self.stats["Losses/Q1 Loss"].append(np.mean(q1loss_total))
        self.stats["Losses/Q2 Loss"].append(np.mean(q2loss_total))
        self.stats["Policy/Entropy Coeff"].append(np.mean(entcoeff_total))
        for _, _reward_signal in self.policy.reward_signals.items():
            _stats = _reward_signal.update(self.training_buffer, n_sequences)
            for _stat, _val in _stats.items():
                self.stats[_stat].append(_val)
        # if self.use_bc:
        #     _bc_loss = self.policy.bc_trainer.update(self.training_buffer)
        #     self.stats["Losses/BC Loss"].append(_bc_loss)

        self.trainer_metrics.end_policy_update()
