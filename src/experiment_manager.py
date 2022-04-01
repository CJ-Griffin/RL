# Useful python libraries
import argparse
import datetime
from tqdm import tqdm

import numpy as np
import gym
import neptune.new as neptune

# My imports
from src.agents import Agent
from src.def_params import skein_dict
from src.run_parameters import TrainParams
from src.generic_utils import init_neptune_log, save_recordings, plot_train_scores
from src.rl_utils import get_env, get_agent


def run_skein(params_list: list[TrainParams], skein_id: str, experiment_name: str):
    for exp_num, exp_params in enumerate(params_list):
        print()
        print()
        print("=" * 214)
        print(("-" * 100) + f" Experiment {exp_num} " + ("-" * 100))
        run_experiment(params=exp_params,
                       skein_id=skein_id,
                       experiment_name=experiment_name)
        print("-" * 214)
        print("=" * 214)
        print()
        print()


def run_experiment(params: TrainParams, skein_id: str, experiment_name: str):
    nept_log = init_neptune_log(params, skein_id, experiment_name)

    print(params)
    env = get_env(params)
    agent = get_agent(env, params)
    env.render()
    agent.render()
    if agent.REQUIRES_TRAINING:
        episode_scores = run_episodic(agent=agent,
                                      env=env,
                                      nept_log=nept_log,
                                      num_episodes=params.num_episodes)
    else:
        episode_scores = []
        print(f"skipping training for {params.agent_name}")

    if not params.agent_name == "HumanAgent":
        eval_score = run_eval(agent, env, nept_log, 200)
        if nept_log is not None:
            nept_log["eval_score"] = eval_score
        print(params.agent_name, eval_score)

    if params.should_render and not params.agent_name == "HumanAgent":
        for ep_no in range(5):
            print("=" * 20 + f" Sample Render {ep_no} " + "=" * 20)
            run_episode(agent, env, should_render=True)

    if nept_log is not None:
        recordings = env.get_recordings()
        if len(recordings) > 0:
            save_recordings(nept_log, recordings)
        nept_log.stop()
    else:
        plot_train_scores(episode_scores)


def run_episodic(agent: Agent,
                 env: gym.Env,
                 num_episodes: int,
                 nept_log: neptune.Run,
                 episode_record_interval: int = 1000):
    episode_scores = []

    ep_iter = tqdm(range(num_episodes))

    for ep_num in ep_iter:
        if ep_num % episode_record_interval == 0:
            env.start_recording()

        num_steps, score = run_episode(agent, env)
        episode_scores.append(score)
        nept_log["ep_scores"].log(score)

        if ep_num % episode_record_interval == 0:
            env.stop_and_log_recording(ep_num)

        if ep_num % 1000 == 0:
            ep_iter.set_description(f"AS = {np.mean(episode_scores[-1000:])}")

    return episode_scores


def run_eval(agent: Agent,
             env: gym.Env,
             nept_log: neptune.Run,
             num_episodes: int) -> float:
    scores = run_episodic(agent=agent,
                          env=env,
                          num_episodes=num_episodes,
                          nept_log=nept_log,
                          episode_record_interval=1)

    return float(np.mean(scores))


def run_episode(agent: Agent,
                env: gym.Env,
                max_steps: int = int(1e4),
                should_render: bool = False) -> (int, float):
    state = env.reset()
    num_steps = 0
    done = False
    rewards = []

    while not done and num_steps <= max_steps:
        num_steps += 1
        if should_render:
            env.render()
        action = agent.act(state)
        next_state, reward, done, info = env.step(action)
        agent.step(state, action, reward, next_state, done)
        state = next_state
        rewards.append(reward)

    env.close()
    score = np.sum(rewards)  # TODO consider different episode scores
    return num_steps, score


if __name__ == '__main__':
    g_prsr = argparse.ArgumentParser()
    g_prsr.add_argument("-e", "--experiment_name",
                        choices=list(skein_dict.keys()) + [None],
                        default=None)
    g_args = g_prsr.parse_args()
    if g_args.experiment_name is not None:
        g_choice = g_args.experiment_name
    else:
        import enquiries

        g_choice = enquiries.choose('Choose an experiment to run: ', skein_dict.keys())
        print(f"CHOSEN: {g_choice}")
    g_skein = skein_dict[g_choice]
    g_time_id = datetime.datetime.now().strftime('%Ym%d_%H%M%S')
    g_skein_id = f"{g_choice}_{g_time_id}"
    if not g_skein[0].should_profile:
        run_skein(g_skein, g_skein_id, g_choice)
    else:
        import cProfile, pstats

        g_profiler = cProfile.Profile()

        g_profiler.enable()
        run_skein(g_skein, g_skein_id, g_choice)
        g_profiler.disable()
        g_stats = pstats.Stats(g_profiler).sort_stats('cumtime')
        g_stats.print_stats()