import numpy as np

from mlagents.trainers.policy import Policy
from .model import BCModel
from mlagents.trainers.demo_loader import demo_to_buffer
from mlagents.trainers.ppo.pre_training import PreTraining


class BCTrainer:
    def __init__(self, policy: Policy, lr, demo_path, anneal_steps, batch_size):
        """
        A BC trainer that can be used inline with RL.
        :param policy: The policy of the learning model
        :param h_size: The size of the the hidden layers of the discriminator
        :param lr: The Learning Rate
        :param demo_path: The path to the demonstration file
        :param signal_strength: The scaling parameter for the reward. The scaled reward will be the unscaled
        reward multiplied by the strength parameter
        """
        super().__init__()
        self.policy = policy
        self.current_lr = lr
        self.model = BCModel(policy.model, lr, anneal_steps)
        _, self.demonstration_buffer = demo_to_buffer(demo_path, policy.sequence_length)
        self.n_sequences = min(
            batch_size, len(self.demonstration_buffer.update_buffer["actions"])
        )
        self.has_updated = False

    def update(self, policy_buffer, max_batches=10):
        """
        Updates model using buffer.
        :param policy_buffer: The policy buffer containing the trajectories for the current policy.
        :param n_sequences: The number of sequences used in each mini batch.
        :param max_batches: The maximum number of batches to use per update.
        :return: The loss of the update.
        """
        # Don't continue training if the learning rate has reached 0, for performance.
        if self.current_lr <= 0:
            return 0

        batch_losses = []
        possible_demo_batches = (
            len(self.demonstration_buffer.update_buffer["actions"]) // self.n_sequences
        )
        possible_batches = possible_demo_batches

        n_epoch = 3
        for epoch in range(n_epoch):
            self.demonstration_buffer.update_buffer.shuffle()
            if max_batches == 0:
                num_batches = possible_batches
            else:
                num_batches = min(possible_batches, max_batches)
            for i in range(num_batches):
                demo_update_buffer = self.demonstration_buffer.update_buffer
                start = i * self.n_sequences
                end = (i + 1) * self.n_sequences
                mini_batch_demo = demo_update_buffer.make_mini_batch(start, end)
                run_out = self._update_batch(mini_batch_demo, self.n_sequences)
                loss = run_out["loss"]
                self.current_lr = run_out["learning_rate"]
                # end for reporting
                batch_losses.append(loss)
        self.has_updated = True
        return np.mean(batch_losses)

    def evaluate(self, current_info, next_info):
        unscaled_reward = np.array(next_info.rewards)
        scaled_reward = 0.0 * unscaled_reward
        return scaled_reward, unscaled_reward

    def _update_batch(self, mini_batch_demo, n_sequences):
        """
        Helper function for update_batch.
        """
        feed_dict = {
            self.policy.model.batch_size: n_sequences,
            self.policy.model.sequence_length: 1,
        }
        if self.policy.model.brain.vector_action_space_type == "continuous":
            feed_dict[self.model.action_in_expert] = mini_batch_demo["actions"].reshape(
                [-1, self.policy.model.brain.vector_action_space_size[0]]
            )
            feed_dict[self.policy.model.epsilon] = np.random.normal(
                size=(1, self.policy.model.act_size[0])
            )
        else:
            feed_dict[self.model.action_in_expert] = mini_batch_demo["actions"].reshape(
                [-1, len(self.policy.model.brain.vector_action_space_size)]
            )
            feed_dict[self.policy.model.action_masks] = np.ones(
                (
                    self.n_sequences,
                    sum(self.policy.model.brain.vector_action_space_size),
                )
            )
        if self.policy.model.brain.vector_observation_space_size > 0:
            apparent_obs_size = (
                self.policy.model.brain.vector_observation_space_size
                * self.policy.model.brain.num_stacked_vector_observations
            )
            feed_dict[self.policy.model.vector_in] = mini_batch_demo[
                "vector_obs"
            ].reshape([-1, apparent_obs_size])
        for i, _ in enumerate(self.policy.model.visual_in):
            visual_obs = mini_batch_demo["visual_obs%d" % i]
            feed_dict[self.policy.model.visual_in[i]] = visual_obs
        # if self.use_recurrent:
        #     feed_dict[self.policy.model.memory_in] = np.zeros([num_sequences, self.m_size])
        #     if not self.policy.model.brain.vector_action_space_type == "continuous":
        #         print(mini_batch.keys())
        #         # feed_dict[self.policy_model.prev_action] = mini_batch['prev_action'] \
        #         #     .reshape([-1, len(self.policy_model.act_size)])
        #         feed_dict[self.policy.model.prev_action] = np.zeros((num_sequences* self.sequence_length,
        #                                                              len(self.policy_model.act_size)))
        self.out_dict = {
            "loss": self.model.loss,
            "update": self.model.update_batch,
            "learning_rate": self.model.annealed_learning_rate,
        }
        network_out = self.policy.sess.run(
            list(self.out_dict.values()), feed_dict=feed_dict
        )
        run_out = dict(zip(list(self.out_dict.keys()), network_out))
        return run_out

