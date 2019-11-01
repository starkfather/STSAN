from __future__ import absolute_import, division, print_function, unicode_literals

import os

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
gpu_id = "3"
os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id

import tensorflow as tf
import numpy as np

gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
        logical_gpus = tf.config.experimental.list_logical_devices('GPU')
        print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
    except RuntimeError as e:
        print(e)

import parameters_nyctaxi as params

from models import Stream_T, ST_SAN

from utils.DataLoader import DataLoader

from random import randint

trans_max = params.trans_train_max

""" Model hyperparameters """
num_layers = 4
d_model = 64
dff = 128
d_final = 256
num_heads = 8
dropout_rate = 0.1
cnn_layers = 3
cnn_filters = 64

""" Training settings"""
BATCH_SIZE = 128
MAX_EPOCHS = 500
earlystop_patience_stream_t = 10
earlystop_patience_stsan = 15
warmup_steps = 4000
verbose_train = 1

""" Data hyperparameters """
load_saved_data = True
num_weeks_hist = 0
num_days_hist = 7
num_intervals_hist = 3
num_intervals_curr = 1
num_intervals_before_predict = 1
num_intervals_enc = (num_weeks_hist + num_days_hist) * num_intervals_hist + num_intervals_curr
local_block_len = 3

stream_t = Stream_T(num_layers,
                    d_model,
                    num_heads,
                    dff,
                    cnn_layers,
                    cnn_filters,
                    4,
                    num_intervals_enc,
                    dropout_rate)

print('Loading tranied Stream-T...')
stream_t_checkpoint_path = "./checkpoints/stream_t_taxi_1"

stream_t_ckpt = tf.train.Checkpoint(Stream_T=stream_t)

stream_t_ckpt_manager = tf.train.CheckpointManager(stream_t_ckpt, stream_t_checkpoint_path,
                                                   max_to_keep=(
                                                           earlystop_patience_stream_t + 1))

stream_t_ckpt.restore(
    stream_t_ckpt_manager.checkpoints[0]).expect_partial()

print('Stream-T restored...')

st_san = ST_SAN(stream_t, num_layers, d_model, num_heads, dff, cnn_layers, cnn_filters,
                num_intervals_enc,
                d_final, dropout_rate)

checkpoint_path = "./checkpoints/ST-SAN_taxi_1"

ckpt = tf.train.Checkpoint(ST_SAN=st_san)

ckpt_manager = tf.train.CheckpointManager(ckpt, checkpoint_path,
                                          max_to_keep=(earlystop_patience_stsan + 1))

ckpt.restore(ckpt_manager.checkpoints[0]).expect_partial()

print('ST-SAN restored...')

data_loader = DataLoader('taxi')

flow_inputs_hist, transition_inputs_hist, ex_inputs_hist, flow_inputs_curr, transition_inputs_curr, \
ex_inputs_curr, ys_transitions, ys = \
    data_loader.generate_data('test',
                              num_weeks_hist,
                              num_days_hist,
                              num_intervals_hist,
                              num_intervals_curr,
                              num_intervals_before_predict,
                              local_block_len,
                              load_saved_data)

sample_index = randint(0, flow_inputs_curr.shape[0])

flow_hist = flow_inputs_hist[sample_index:(sample_index + 1), :, :, :, :]
trans_hist = transition_inputs_hist[sample_index:(sample_index + 1), :, :, :, :]
ex_hist = ex_inputs_hist[sample_index:(sample_index + 1), :, :]
flow_curr = flow_inputs_curr[sample_index:(sample_index + 1), :, :, :, :]
trans_curr = transition_inputs_curr[sample_index:(sample_index + 1), :, :, :, :]
ex_curr = ex_inputs_curr[sample_index:(sample_index + 1), :, :]

predictions_t, att_t = stream_t(trans_hist, ex_hist, trans_curr, ex_curr, training=False)
predictions_f, att_f = st_san(flow_hist, trans_hist, ex_hist, flow_curr, trans_curr, ex_curr,
                              training=False)

predictions_t = np.array(predictions_t, dtype=np.float32)
predictions_f = np.array(predictions_f, dtype=np.float32)
att_t = np.array(att_t['decoder_layer4_block2'], dtype=np.float32)
att_f = np.array(att_f['decoder_layer4_block2'], dtype=np.float32)
predictions_t, predictions_f, att_t, att_f = np.squeeze([predictions_t, predictions_f, att_t, att_f])
