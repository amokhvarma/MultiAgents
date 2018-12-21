# Python Imports
from collections import defaultdict
from copy import deepcopy
import datetime
import gc
import matplotlib.pyplot as plt
import numpy as np
import os
import pickle
import psutil
import sys
import time

# My Python Imports
import log
import parameter_estimation
import train_data
import posimulator
import POUCT

# ============= Set Configurations ============
# System Configuration
sys.setrecursionlimit(2000)
memory_usage = 0

# Simulation Configuration
sim_path = None

types = ['l1', 'l2', 'f1', 'f2']
type_selection_mode = None

iteration_max = None
max_depth = None

do_estimation = True
train_mode = None
parameter_estimation_mode = None

generated_data_number = None
reuse_tree = None

mcts_mode = None
PF_add_threshold = None
PF_del_threshold = None
PF_weight = 0.0
apply_adversary = False


# ============= Set Input/Output ============
if len(sys.argv) > 1:
    input_folder = sys.argv[1]
else:
    input_folder = log.get_input_folder()
output_folder = log.create_output_folder()

# ============= Read Configuration ============
# 1. Reading the sim configuration file
info = defaultdict(list)
with open(input_folder+'poconfig.csv') as info_read:
    for line in info_read:
        data = line.strip().split(',')
        key, val = data[0], data[1:]
        info[key].append(val)

# 2. Getting the parameters
for k, v in info.items():

    if 'sim_path' in k:
        sim_path = input_folder + str(v[0][0]).strip()

    if 'type_selection_mode' in k:
        type_selection_mode = str(v[0][0]).strip()

    if 'iteration_max' in k:
        iteration_max = int(v[0][0])

    if 'max_depth' in k:
        max_depth = int(v[0][0])

    if 'do_estimation' in k:
        if v[0][0] == 'False':
            do_estimation = False
        else:
            do_estimation = True

    if 'train_mode' in k:
        train_mode = str(v[0][0]).strip()

    if 'parameter_estimation_mode' in k:
        parameter_estimation_mode = str(v[0][0]).strip()

    if 'generated_data_number' in k:
        generated_data_number = int(v[0][0])

    if 'reuseTree' in k:
        reuse_tree = v[0][0]

    if 'mcts_mode' in k:
        mcts_mode = str(v[0][0]).strip()

    if 'PF_add_threshold' in k:
        PF_add_threshold = float(v[0][0])

    if 'PF_del_threshold' in k:
        PF_del_threshold = float(v[0][0])

    if 'PF_weight' in k:
        PF_weight = float(v[0][0])

    if 'apply_adversary' in k:
        if v[0][0] == 'False':
            apply_adversary = False
        else:
            apply_adversary = True

sim_configuration = {'sim_path':sim_path,\
    'types':types,'type_selection_mode':type_selection_mode,\
    'iteration_max':iteration_max,'max_depth':max_depth,\
    'do_estimation':do_estimation,'train_mode':train_mode,\
    'parameter_estimation_mode':parameter_estimation_mode,\
    'generated_data_number':generated_data_number,\
    'reuse_tree':reuse_tree,'mcts_mode':mcts_mode,\
    'PF_add_threshold':PF_add_threshold,\
    'PF_del_threshold':PF_del_threshold,\
    'PF_weight':PF_weight,'apply_adversary':apply_adversary}

# ============= Set Simulation and Log File ============
main_sim = posimulator.POSimulator()
main_sim.loader(sim_path)

log_file = log.create_log_file(output_folder + "log.txt")
log_file.write('Grid Size: {} - {} Items - {} Agents - {} Obstacles\n'.\
        format(main_sim.dim_w,len(main_sim.items),len(main_sim.agents),len(main_sim.obstacles)))
log.write_configurations(log_file,sim_configuration)
log_file.write('***** Initial map *****\n')
log.write_map(log_file,main_sim)

# ============= Simulation Initialization ==================
# 1. Log Variables Init
begin_time = time.time()
begin_cpu_time = psutil.cpu_times()
used_mem_before = psutil.virtual_memory().used

# 2. Sim estimation Init
polynomial_degree = 4
agents_parameter_estimation = []
agents_previous_step_info = []

# 3. Ad hoc Agents
if main_sim.main_agent is not None:
    main_agent = main_sim.main_agent
    search_tree = None

    main_sim.main_agent.initialise_visible_agents(main_sim,generated_data_number, PF_add_threshold, train_mode,
                                              type_selection_mode, parameter_estimation_mode, polynomial_degree,apply_adversary)
    uct = POUCT.POUCT(iteration_max, max_depth, do_estimation, mcts_mode, apply_adversary,enemy=False)
    main_sim.main_agent.initialise_uct(uct)

if apply_adversary:
    enemy_agent = main_sim.enemy_agent
    enemy_search_tree = None
    if main_sim.enemy_agent is not None:
        main_sim.enemy_agent.initialise_visible_agents(main_sim,generated_data_number, PF_add_threshold, train_mode,
                                                  type_selection_mode, parameter_estimation_mode, polynomial_degree,apply_adversary)
        enemy_uct = POUCT.POUCT(iteration_max, max_depth, do_estimation, mcts_mode,apply_adversary, enemy=True )
        main_sim.enemy_agent.initialise_uct(enemy_uct)


for v_a in main_sim.main_agent.visible_agents:
    v_a.choose_target_state = deepcopy(main_sim)

# ============= Start Simulation ==================
time_step = 0
while main_sim.items_left() > 0:
    progress = 100 * (len(main_sim.items) - main_sim.items_left())/len(main_sim.items)
    sys.stdout.write("Experiment progress: %d%% | step: %d   \r" % (progress,time_step) )
    sys.stdout.flush()

    log_file.write('***** Iteration #'+str(time_step)+' *****\n')

    print '-------------------------------Iteration number ', time_step, '--------------------------------------'

    if main_sim.main_agent is not None:
        print('****** UPDATE UNKNOWN AGENT **********')
        main_sim.main_agent.previous_state = main_sim.copy()
        main_sim.main_agent.update_unknown_agents(main_sim)

    print('****** MOVE AGENT **********')
    for i in range(len(main_sim.agents)):
        main_sim.agents[i] = main_sim.move_a_agent(main_sim.agents[i])

        print('main_sim.agents[i].next_action=', main_sim.agents[i].next_action)
        # print 'agent ',main_sim.agents[i].index,' target: ', main_sim.agents[i].get_memory()

    print('****** Movement of Intelligent agent based on MCTS ****************************************************')
    if main_sim.main_agent is not None:
        r,enemy_action_prob,search_tree = main_sim.main_agent.move(reuse_tree, main_sim, search_tree, time_step)

    if main_sim.enemy_agent is not None:
        # print('****** Movement of Enemy agent based on MCTS ****************************************************')
        r, main_action_prob,enemy_search_tree = main_sim.enemy_agent.move(reuse_tree, main_sim, enemy_search_tree, time_step)

    actions = main_sim.update_all_A_agents(False)
    main_sim.do_collaboration()
    main_sim.main_agent.update_unknown_agents_status(main_sim)
    main_sim.draw_map()


    print '********* Estimation for selfish agents ******'
    if do_estimation:
        main_sim.main_agent.estimation(time_step,main_sim,enemy_action_prob,actions )

    time_step += 1
    # print '---x_train_set in time step ', time_step ,' is :  '
    # for xts in x_train_set:
    #     print xts

    if main_sim.items_left() == 0:
        break

    search_tree = uct.update_belief_state(main_sim,search_tree)
    print "main agent left items", main_sim.main_agent.items_left()

    print "left items", main_sim.items_left()
    gc.collect()

    print('***********************************************************************************************************')
progress = 100 * (len(main_sim.items) - main_sim.items_left())/len(main_sim.items)
sys.stdout.write("Experiment progress: %d%% | step: %d   \n" % (progress,time_step) )
    
# ============= Finish Simulation ==================
end_time = time.time()
used_mem_after = psutil.virtual_memory().used
end_cpu_time = psutil.cpu_times()
memory_usage = used_mem_after - used_mem_before

log.print_result(main_sim,  time_step, begin_time, end_time,\
    mcts_mode, parameter_estimation_mode, type_selection_mode,\
    iteration_max,max_depth, generated_data_number,reuse_tree,\
    PF_add_threshold, PF_weight,\
    end_cpu_time, memory_usage,log_file,output_folder)
