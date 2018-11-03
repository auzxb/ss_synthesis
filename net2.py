import tensorflow as tf


import matplotlib.pyplot as plt

import os
import sys

sys.path.insert(0, './griffin_lim/')
import audio_utilities
import time
import numpy as np
from six.moves import xrange  # pylint: disable=redefined-builtin
import h5py
import soundfile as sf
import config
from data_pipeline import data_gen
import modules_tf as modules
import utils
from reduce import mgc_to_mfsc

def one_hotize(inp, max_index=41):
    # output = np.zeros((inp.shape[0],inp.shape[1],max_index))
    # for i, index in enumerate(inp):
    #     output[i,index] = 1
    # import pdb;pdb.set_trace()
    output = np.eye(max_index)[inp.astype(int)]
    # import pdb;pdb.set_trace()
    # output = np.eye(max_index)[inp]
    return output
def binary_cross(p,q):
    return -(p * tf.log(q + 1e-12) + (1 - p) * tf.log( 1 - q + 1e-12))

def train(_):
    stat_file = h5py.File(config.stat_dir+'stats.hdf5', mode='r')
    max_feat = np.array(stat_file["feats_maximus"])
    min_feat = np.array(stat_file["feats_minimus"])
    with tf.Graph().as_default():
        
        input_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,66),name='input_placeholder')
        tf.summary.histogram('inputs', input_placeholder)
        is_train = tf.placeholder(tf.bool, name="is_train")

        output_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,66),name='output_placeholder')

        rand_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,1),name='random_placeholder')

        # output_phase_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,config.input_features),name='output_phase_placeholder')

        f0_target_placeholder_midi = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len),name='f0_target_midi_placeholder')
        onehot_labels_f0_midi = tf.one_hot(indices=tf.cast(f0_target_placeholder_midi, tf.int32), depth=57)

        f0_input_placeholder_midi = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len, 57),name='f0_input_placeholder')

        # f0_target_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len),name='f0_target_placeholder')
        # onehot_labels_f0 = tf.one_hot(indices=tf.cast(f0_target_placeholder, tf.int32), depth=256)

        # f0_input_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len, 256),name='f0_input_placeholder')

        pho_input_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len, 42),name='pho_input_placeholder')

        prob = tf.placeholder_with_default(1.0, shape=())

        # tf.summary.histogram('targets', target_placeholder)
        
        labels = tf.placeholder(tf.int32, shape=(config.batch_size,config.max_phr_len),name='phoneme_placeholder')
        onehot_labels = tf.one_hot(indices=tf.cast(labels, tf.int32), depth=42)

        real_logs = tf.placeholder(tf.float32, shape=(config.batch_size,1),name='real_logits_placeholder')

        fake_logs = tf.placeholder(tf.float32, shape=(config.batch_size,1),name='fake_logits_placeholder')

        singer_labels = tf.placeholder(tf.int32, shape=(config.batch_size),name='singer_id_placeholder')
        onehot_labels_singer = tf.one_hot(indices=tf.cast(singer_labels, tf.int32), depth=12)

        singer_labels_2 = tf.placeholder(tf.int32, shape=(config.batch_size),name='singer_id_placeholder_2')
        onehot_labels_singer_2 = tf.one_hot(indices=tf.cast(singer_labels_2, tf.int32), depth=12)

        singer_embedding_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,256),name='singer_embedding_placeholder')





        with tf.variable_scope('F0_Model_midi') as scope:
            f0_logits_midi = modules.f0_network(input_placeholder, prob)
            f0_classes_midi = tf.argmax(f0_logits_midi, axis=-1)
            f0_probs_midi = tf.nn.softmax(f0_logits_midi)

        # with tf.variable_scope('F0_Model_256') as scope:
        #     f0_logits = modules.f0_network_2(singer_embedding_placeholder, f0_input_placeholder_midi, pho_input_placeholder, prob)
        #     f0_classes = tf.argmax(f0_logits, axis=-1)
        #     f0_probs = tf.nn.softmax(f0_logits)

        with tf.variable_scope('Final_Model') as scope:
            voc_output = modules.final_net(rand_placeholder, singer_embedding_placeholder, f0_input_placeholder_midi, pho_input_placeholder, prob)
            voc_output_decoded = tf.nn.sigmoid(voc_output)

        # with tf.variable_scope('Final_Model_Phase') as scope:
        #     voc_output_phase = modules.final_net_phase(singer_embedding_placeholder, f0_input_placeholder, pho_input_placeholder, input_placeholder, prob)
        #     voc_output_phase_decoded = tf.nn.sigmoid(voc_output_phase)

        with tf.variable_scope('Discriminator') as scope: 
                singer_real, phonemes_real, D_real = modules.GAN_discriminator(output_placeholder, f0_input_placeholder_midi, pho_input_placeholder, singer_embedding_placeholder, is_train)
                scope.reuse_variables()
                singer_fake, phonemes_fake, D_fake = modules.GAN_discriminator(voc_output, f0_input_placeholder_midi, pho_input_placeholder, singer_embedding_placeholder, is_train)

        with tf.variable_scope('phone_Model') as scope:
            regularizer = tf.contrib.layers.l2_regularizer(scale=0.1)
            pho_logits = modules.phone_network(input_placeholder, prob, regularizer = regularizer)
            pho_classes = tf.argmax(pho_logits, axis=-1)
            pho_probs = tf.nn.softmax(pho_logits)

            

        with tf.variable_scope('singer_Model') as scope:
            singer_embedding, singer_logits = modules.singer_network(input_placeholder, prob)
            singer_classes = tf.argmax(singer_logits, axis=-1)
            singer_probs = tf.nn.softmax(singer_logits)

            scope.reuse_variables()

            # import pdb;pdb.set_trace()

            singer_embedding_real, singer_logits_real = modules.singer_network(voc_output, prob)
            singer_classes_real = tf.argmax(singer_logits_real, axis=-1)
            singer_probs_real = tf.nn.softmax(singer_logits_real)

            # singer_embedding_false, singer_logits_real = modules.singer_network(voc_output_decoded, prob)
            # singer_classes_false = tf.argmax(singer_logits_false, axis=-1)
            # singer_probs_real = tf.nn.softmax(singer_logits_false)



        varys = tf.trainable_variables()

        final_vars = [x for x in varys if x.name.startswith('Final_Model')]

        d_params = [v for v in varys if v.name.startswith('Discriminator/D')]




        # f0_loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels_f0, logits=f0_logits))

        f0_loss_midi = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels_f0_midi, logits=f0_logits_midi))

        pho_weights = tf.reduce_sum(config.phonemas_weights * onehot_labels, axis=-1)

        unweighted_losses = tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels, logits=pho_logits)

        weighted_losses = unweighted_losses * pho_weights

        pho_loss = tf.reduce_mean(weighted_losses)

        reg_variables = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES)

        reg_term = tf.contrib.layers.apply_regularization(regularizer, reg_variables)

        pho_loss+=reg_term

        # import pdb;pdb.set_trace()

        singer_loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels_singer, logits=singer_logits))

        singer_loss_2 = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels_singer_2, logits=singer_logits_real))

        # D_loss_real = -tf.reduce_mean(tf.log(D_real + 1e-10))
        # D_loss_fake = -tf.reduce_mean(tf.log(1. - (D_fake + 1e-10)))
        D_loss_real = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(labels=real_logs, logits=D_real+1e-12))
        D_loss_fake = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(labels=fake_logs, logits=D_fake+1e-12))

        singer_loss_real = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels_singer, logits=singer_real))

        unweighted_losses_real = tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels, logits=phonemes_real)

        weighted_losses_real = unweighted_losses_real * pho_weights

        pho_loss_real = tf.reduce_mean(weighted_losses_real)

        D_loss = D_loss_real+D_loss_fake + pho_loss_real +singer_loss_real

        # G_loss_GAN = -tf.reduce_mean(tf.log(D_fake + 1e-10))
        G_loss_GAN = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(labels=real_logs, logits=D_fake+1e-12)) 

        unweighted_losses_fake = tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels, logits=phonemes_fake)

        weighted_losses_fake = unweighted_losses_fake * pho_weights

        pho_loss_fake = tf.reduce_mean(weighted_losses_fake)
        singer_loss_fake = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=onehot_labels_singer, logits=singer_fake))


        G_loss_GAN+= pho_loss_fake
        G_loss_GAN+=singer_loss_fake

        

        reconstruct_loss = tf.reduce_sum(tf.nn.sigmoid_cross_entropy_with_logits(labels= output_placeholder, logits=voc_output)) * config.lamda 
        # - tf.reduce_mean(tf.abs(voc_output[:,:-1,:] - voc_output[:,1:,:]))* config.lamda*0.001



        # G_loss_GAN = tf.reduce_sum(tf.abs(voc_output[:,:-1,:] - voc_output[:,1:,:])* config.lamda*0.01)

        final_loss =  G_loss_GAN +reconstruct_loss

        # reconstruct_loss_phase = tf.reduce_sum(tf.nn.sigmoid_cross_entropy_with_logits(labels= output_phase_placeholder, logits=voc_output_phase))




        # pho_loss = tf.reduce_mean(tf.losses.softmax_cross_entropy(onehot_labels=onehot_labels, logits=pho_logits)*(1-target_placeholder[:,:,-1:])) *60

        # pho_loss = tf.reduce_sum(tf.abs(pho_probs - onehot_labels))

        pho_acc = tf.metrics.accuracy(labels=labels, predictions=pho_classes)

        # f0_acc = tf.metrics.accuracy(labels=f0_target_placeholder, predictions=f0_classes)

        f0_acc_midi = tf.metrics.accuracy(labels=f0_target_placeholder_midi, predictions=f0_classes_midi)

        singer_acc = tf.metrics.accuracy(labels=singer_labels , predictions=singer_classes)

        singer_acc_real = tf.metrics.accuracy(labels=singer_labels_2 , predictions=singer_classes_real)

        singer_acc_false = tf.metrics.accuracy(labels=singer_labels_2 , predictions=singer_classes_real)


        pho_acc_val = tf.metrics.accuracy(labels=labels, predictions=pho_classes)

        # f0_acc_val = tf.metrics.accuracy(labels=f0_target_placeholder, predictions=f0_classes)

        f0_acc_midi_val = tf.metrics.accuracy(labels=f0_target_placeholder_midi, predictions=f0_classes_midi)

        singer_acc_val = tf.metrics.accuracy(labels=singer_labels , predictions=singer_classes)



        pho_summary = tf.summary.scalar('pho_loss', pho_loss)

        pho_acc_summary = tf.summary.scalar('pho_accuracy', pho_acc[0])

        pho_acc_summary_val = tf.summary.scalar('pho_accuracy_val', pho_acc_val[0])

        # ap_summary = tf.summary.scalar('ap_loss', ap_loss)

        # f0_summary = tf.summary.scalar('f0_loss', f0_loss)

        reconstruct_summary = tf.summary.scalar('reconstruct_loss', reconstruct_loss)

        # reconstruct_phase_summary = tf.summary.scalar('reconstruct_loss_phase', reconstruct_loss_phase)

        # f0_acc_summary = tf.summary.scalar('f0_accuracy', f0_acc[0])

        # f0_acc_summary_val = tf.summary.scalar('f0_accuracy_val', f0_acc_val[0])

        f0_summary_midi = tf.summary.scalar('f0_loss_midi', f0_loss_midi)

        f0_acc_summary_midi = tf.summary.scalar('f0_accuracy_midi', f0_acc_midi[0])

        f0_acc_summary_midi_val = tf.summary.scalar('f0_accuracy_midi_val', f0_acc_midi_val[0])

        singer_summary = tf.summary.scalar('singer_loss', singer_loss)

        singer_acc_summary = tf.summary.scalar('singer_accuracy', singer_acc[0])

        singer_acc_summary_real = tf.summary.scalar('singer_accuracy_real', singer_acc_real[0])

        singer_acc_summary_false = tf.summary.scalar('singer_accuracy_false', singer_acc_false[0])

        singer_acc_summary_val = tf.summary.scalar('singer_accuracy_val', singer_acc_val[0])

        summary = tf.summary.merge([ f0_summary_midi, pho_summary, singer_summary, reconstruct_summary, pho_acc_summary,  f0_acc_summary_midi, singer_acc_summary, singer_acc_summary_real, singer_acc_summary_false ])

        summary_val = tf.summary.merge([f0_summary_midi, pho_summary, singer_summary, reconstruct_summary, pho_acc_summary_val,  f0_acc_summary_midi_val, singer_acc_summary_val ])

        # vuv_summary = tf.summary.scalar('vuv_loss', vuv_loss)

        # loss_summary = tf.summary.scalar('total_loss', loss)

        global_step = tf.Variable(0, name='global_step', trainable=False)

        global_step_pho = tf.Variable(0, name='global_step_pho', trainable=False)

        global_step_singer = tf.Variable(0, name='global_step_singer', trainable=False)

        # global_step_f0 = tf.Variable(0, name='global_step_f0', trainable=False)

        global_step_re = tf.Variable(0, name='global_step_re', trainable=False)

        global_step_dis = tf.Variable(0, name='global_step_dis', trainable=False)

        global_step_cgan = tf.Variable(0, name='global_step_cgan', trainable=False)

        # global_step_re_phase = tf.Variable(0, name='global_step_re_phase', trainable=False)



        f0_optimizer = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        f0_optimizer_midi = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        pho_optimizer = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        singer_optimizer = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        re_optimizer = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        dis_optimizer = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        cgan_optimizer = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        # re_phase_optimizer = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        # optimizer_f0 = tf.train.AdamOptimizer(learning_rate = config.init_lr)

        # f0_train_function = f0_optimizer.minimize(f0_loss, global_step= global_step_f0)

        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)

        

        f0_train_function_midi = f0_optimizer.minimize(f0_loss_midi, global_step= global_step)

        pho_train_function = pho_optimizer.minimize(pho_loss, global_step = global_step_pho)

        singer_train_function = pho_optimizer.minimize(singer_loss, global_step = global_step_singer)

        # import pdb;pdb.set_trace()

        

        with tf.control_dependencies(update_ops):
            re_train_function = re_optimizer.minimize(final_loss, global_step = global_step_re, var_list=final_vars)

            dis_train_function = dis_optimizer.minimize(D_loss, global_step = global_step_dis, var_list=d_params)

        cgan_train_function = re_optimizer.minimize(singer_loss_2, global_step = global_step_cgan, var_list=final_vars)

        # re_phase_train_function = re_optimizer.minimize(reconstruct_loss_phase, global_step = global_step_re_phase)

        # train_f0 = optimizer.minimize(f0_loss, global_step= global_step)

        # train_harm = optimizer.minimize(harm_loss, global_step= global_step)

        # train_ap = optimizer.minimize(ap_loss, global_step= global_step)

        # train_f0 = optimizer.minimize(f0_loss, global_step= global_step)

        # train_vuv = optimizer.minimize(vuv_loss, global_step= global_step)

        # import pdb;pdb.set_trace()

        

        init_op = tf.group(tf.global_variables_initializer(), tf.local_variables_initializer())
        saver = tf.train.Saver(max_to_keep= config.max_models_to_keep)
        sess = tf.Session()

        sess.run(init_op)

        ckpt = tf.train.get_checkpoint_state(config.log_dir)

        if ckpt and ckpt.model_checkpoint_path:
            print("Using the model in %s"%ckpt.model_checkpoint_path)
            saver.restore(sess, ckpt.model_checkpoint_path)


        train_summary_writer = tf.summary.FileWriter(config.log_dir+'train/', sess.graph)
        val_summary_writer = tf.summary.FileWriter(config.log_dir+'val/', sess.graph)

        
        start_epoch = int(sess.run(tf.train.get_global_step())/(config.batches_per_epoch_train))

        print("Start from: %d" % start_epoch)
        f0_accs = []
        for epoch in xrange(start_epoch, config.num_epochs):
            val_f0_accs = []

            # if epoch>30:
            #     sec_mode = 0
            # else:
            #     sec_mode = 0


            data_generator = data_gen(sec_mode = 0)
            start_time = time.time()



            epoch_loss_f0_midi = 0
            epoch_acc_f0_midi = 0

            # epoch_loss_f0 = 0
            # epoch_acc_f0 = 0
            
            epoch_loss_pho = 0
            epoch_acc = 0

            epoch_loss_singer = 0
            epoch_acc_singer = 0

            epoch_total_loss = 0

            epoch_dis_loss = 0

            # epoch_total_loss_phase = 0

            epoch_loss_f0_midi_val = 0
            epoch_acc_f0_midi_val = 0

            # epoch_loss_f0_val = 0
            # epoch_acc_f0_val = 0
            
            epoch_loss_pho_val = 0
            epoch_acc_val = 0

            epoch_loss_singer_val = 0
            epoch_acc_singer_val = 0

            epoch_total_loss_val = 0

            epoch_loss_re_real = 0
            epoch_loss_re_false = 0
            epoch_loss_cg_real = 0
            epoch_loss_cg_false = 0
            epoch_acc_real = 0
            epoch_acc_false = 0

            # epoch_total_loss_phase_val = 0


            batch_num = 0
            batch_num_val = 0

            val_generator = data_gen(mode='val')

            pho_count = 0
            pho_count_val = 0
            flag_count = 0

            # val_generator = get_batches(train_filename=config.h5py_file_val, batches_per_epoch=config.batches_per_epoch_val)

            with tf.variable_scope('Training'):

                for inputs, feats_targets, targets_f0_1, targets_f0_2, pho_targs, singer_ids, Flag in data_generator:

                    # import pdb;pdb.set_trace()

                    f0_1_one_hot = one_hotize(targets_f0_1, max_index=256)

                    f0_2_one_hot = one_hotize(targets_f0_2, max_index=57)

                    if Flag:
                        pho_one_hot = one_hotize(pho_targs, max_index=42)

                    featies = feats_targets

                    input_noisy = np.clip(featies + np.random.rand(config.batch_size, config.max_phr_len,66)*np.clip(np.random.rand(1),0.0,config.noise_threshold), 0.0, 1.0)

                    _, step_loss_f0_midi, step_acc_f0_midi = sess.run([f0_train_function_midi, f0_loss_midi, f0_acc_midi], feed_dict={input_placeholder: input_noisy,f0_target_placeholder_midi: targets_f0_2})
                    if Flag:
                        flag_count+=1
                        _, step_loss_singer, step_acc_singer, s_embed = sess.run([singer_train_function, singer_loss, singer_acc, singer_embedding], feed_dict={input_placeholder: featies,singer_labels: singer_ids, prob:0.75})
                    else:
                         s_embed = sess.run(singer_embedding, feed_dict={input_placeholder: input_noisy})

                    # real, fake, = sess.run([D_real, D_fake], 
                    #     feed_dict={f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: feats_targets, prob:0.8,singer_embedding_placeholder: s_embed}) 
                    # import pdb;pdb.set_trace()





                    teacher_train = np.random.rand(1)<0.5

                    re_logits = np.clip(np.random.rand(config.batch_size,1), 0.8,1.0)

                    random_inputs = np.random.rand(config.batch_size, config.max_phr_len, 1)

                    re_logits_gen = np.ones((config.batch_size,1))

                    fa_logits = np.clip(np.random.rand(config.batch_size,1), 0.0,0.2)

                    # import pdb;pdb.set_trace()

                    if teacher_train:
                        # _, step_loss_f0, step_acc_f0 = sess.run([f0_train_function, f0_loss, f0_acc], feed_dict={input_placeholder: input_noisy,singer_embedding_placeholder: s_embed, f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder:pho_one_hot, f0_target_placeholder: targets_f0_1, prob:1.0})
                        if Flag:
                            _, step_loss_pho, step_acc_pho = sess.run([pho_train_function, pho_loss, pho_acc], feed_dict={input_placeholder: input_noisy,labels: pho_targs, prob:0.75})
                            # _, step_loss_total = sess.run([re_train_function, reconstruct_loss], feed_dict={f0_input_placeholder: f0_1_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:0.8})

                         
                           # outs_real = 

                            # if epoch > 250:
                            #     _,_ ,step_loss_total, step_re_loss, step_singer_loss_real, step_singer_acc_real = sess.run([re_train_function, cgan_train_function, final_loss, reconstruct_loss, singer_loss_2,singer_acc_real],
                            #      feed_dict={f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:0.8,singer_labels_2: singer_ids})
                            #     _,step_loss_dis = sess.run([dis_train_function, D_loss], 
                            #         feed_dict={f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:0.8,singer_labels_2: singer_ids})
                            #     s_embed_2, singer_ids_2 = utils.shuffle_two(s_embed, singer_ids)
                            #     _,_, step_loss_total_2, step_re_loss_2, step_singer_loss_false, step_singer_acc_false = sess.run([re_train_function, cgan_train_function, final_loss, reconstruct_loss, singer_loss_2,singer_acc_false], feed_dict={f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed_2, prob:0.8,singer_labels_2: singer_ids_2})
                            # else:
                            
                            _,step_loss_total, step_re_loss, step_gen_loss = sess.run([re_train_function, final_loss, reconstruct_loss, G_loss_GAN], feed_dict={rand_placeholder:random_inputs, f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:0.8, real_logs:re_logits_gen, is_train : True, labels: pho_targs,singer_labels: singer_ids})
                

                            # _= sess.run(dis_train_function, 
                            #     feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: (input_noisy*2)-1, prob:0.8,singer_embedding_placeholder: s_embed, real_logs:re_logits, fake_logs : fa_logits, is_train : True})
                            
                            # _= sess.run(dis_train_function, 
                            #     feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: (input_noisy*2)-1, prob:0.8,singer_embedding_placeholder: s_embed, real_logs:re_logits, fake_logs : fa_logits, is_train : True})
                            _,step_loss_dis = sess.run( [dis_train_function, D_loss], 
                                feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: (input_noisy*2)-1, prob:0.8,singer_embedding_placeholder: s_embed, real_logs:re_logits, fake_logs : fa_logits, is_train : True, labels: pho_targs,singer_labels: singer_ids})
                        else:
                            pho_outs = sess.run(pho_probs, feed_dict = {input_placeholder: input_noisy,f0_input_placeholder_midi: f0_2_one_hot} )
                            _, step_re_loss = sess.run([re_train_function, reconstruct_loss], feed_dict={f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_outs, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:1.0, input_placeholder: featies})

                        # _, step_loss_total_phase = sess.run([re_phase_train_function, reconstruct_loss_phase], feed_dict={input_placeholder:input_noisy, f0_input_placeholder: one_hotize(targets_f0_1, max_index=256), pho_input_placeholder: one_hotize(pho_targs, max_index=41),singer_embedding_placeholder: s_embed, prob:0.5, output_phase_placeholder: phase_targets})
                    
                    else:

                        f0_outputs_1 = sess.run(f0_probs_midi, feed_dict = {input_placeholder: input_noisy,singer_embedding_placeholder: s_embed} )
                        if Flag:
                            _, step_loss_pho, step_acc_pho = sess.run([pho_train_function, pho_loss, pho_acc], feed_dict={input_placeholder: input_noisy,f0_input_placeholder_midi: f0_outputs_1, labels: pho_targs, prob:1.0})
                            pho_outs = sess.run(pho_probs, feed_dict = {input_placeholder: input_noisy,f0_input_placeholder_midi: f0_2_one_hot} )
                            # _, step_loss_f0, step_acc_f0 = sess.run([f0_train_function, f0_loss, f0_acc], feed_dict={input_placeholder: input_noisy,singer_embedding_placeholder: s_embed, f0_input_placeholder_midi: f0_outputs_1, f0_target_placeholder: targets_f0_1, pho_input_placeholder: pho_outs, prob:1.0})
                            # f0_outputs_2 = sess.run(f0_probs, feed_dict={input_placeholder: input_noisy,singer_embedding_placeholder: s_embed, 
                            #     f0_input_placeholder_midi: f0_outputs_1, pho_input_placeholder: pho_outs} )
                            # if epoch > 250:
                            #     _,_,step_loss_total, step_re_loss, step_singer_loss_real, step_singer_acc_real = sess.run([re_train_function, cgan_train_function, final_loss, reconstruct_loss, singer_loss_2,singer_acc_real], feed_dict={f0_input_placeholder_midi: f0_outputs_1, pho_input_placeholder: pho_outs, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:1.0, input_placeholder: featies,singer_labels_2: singer_ids})

                            #     s_embed_2, singer_ids_2 = utils.shuffle_two(s_embed, singer_ids)

                            #     _,_, step_loss_total_2, step_re_loss_2, step_singer_loss_false, step_singer_acc_false = sess.run([re_train_function, cgan_train_function, final_loss, reconstruct_loss, singer_loss_2,singer_acc_false], feed_dict={f0_input_placeholder_midi: f0_outputs_1, pho_input_placeholder: pho_outs, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed_2, prob:1.0, input_placeholder: featies,singer_labels_2: singer_ids_2})
                            #     _,step_loss_dis = sess.run([dis_train_function, D_loss], 
                            #         feed_dict={f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:0.8,singer_labels_2: singer_ids})
                            # else:

                            _,step_loss_total, step_re_loss, step_gen_loss = sess.run([re_train_function, final_loss, reconstruct_loss, G_loss_GAN], feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: f0_outputs_1, pho_input_placeholder: pho_outs, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:1.0, input_placeholder: featies,singer_labels_2: singer_ids, real_logs:re_logits_gen, is_train:True,labels: pho_targs,singer_labels: singer_ids})

                            # _ = sess.run(dis_train_function, 
                            #     feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: (input_noisy*2)-1,singer_embedding_placeholder: s_embed, prob:0.8, real_logs:re_logits, fake_logs : fa_logits, is_train:True})

                            # _ = sess.run(dis_train_function, 
                            #     feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: (input_noisy*2)-1,singer_embedding_placeholder: s_embed, prob:0.8, real_logs:re_logits, fake_logs : fa_logits, is_train:True})

                            _,step_loss_dis = sess.run([dis_train_function, D_loss], 
                                feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: (input_noisy*2)-1,singer_embedding_placeholder: s_embed, prob:0.8, real_logs:re_logits, fake_logs : fa_logits, is_train:True, labels: pho_targs,singer_labels: singer_ids})


                        else:
                            pho_outs = sess.run(pho_probs, feed_dict = {input_placeholder: input_noisy,f0_input_placeholder_midi: f0_2_one_hot} )
                            _, step_re_loss = sess.run([re_train_function,  reconstruct_loss], feed_dict={f0_input_placeholder_midi: f0_outputs_1, pho_input_placeholder: pho_outs, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed, prob:1.0, input_placeholder: featies})
                            # import pdb;pdb.set_trace()




                        # import pdb;pdb.set_trace()
                        # spec_output = sess.run(voc_output_decoded,feed_dict={f0_input_placeholder: f0_outputs_2, pho_input_placeholder: pho_outs, output_placeholder: inputs,singer_embedding_placeholder: s_embed, prob:0.5} )
                        # _, step_loss_total_phase = sess.run([re_phase_train_function, reconstruct_loss_phase], feed_dict={input_placeholder:spec_output, f0_input_placeholder: f0_outputs_2, pho_input_placeholder: pho_outs,singer_embedding_placeholder: s_embed, prob:0.5, output_phase_placeholder: phase_targets})

                    #     # import pdb;pdb.set_trace()

                    if Flag:
                        epoch_loss_pho+=step_loss_pho
                        epoch_acc+=step_acc_pho[0]
                        pho_count+=1

                    

                    # epoch_loss_f0+=step_loss_f0
                    # epoch_acc_f0+=step_acc_f0[0]

                    epoch_loss_f0_midi+=step_loss_f0_midi

                    epoch_dis_loss+=step_loss_dis

                    epoch_loss_cg_real += step_gen_loss

                    epoch_acc_f0_midi+=step_acc_f0_midi[0]

                    if Flag:
                        epoch_loss_singer+=step_loss_singer
                        epoch_acc_singer+=step_acc_singer[0]
                        epoch_total_loss+=step_loss_total
                    
                    epoch_loss_re_real += step_re_loss
                    # if epoch>250:
                    #     epoch_loss_re_false += step_re_loss_2
                    #     epoch_loss_cg_real += step_singer_loss_real
                    #     epoch_loss_cg_false += step_singer_loss_false
                    #     epoch_acc_real += step_singer_acc_real[0] 
                    #     epoch_acc_false += step_singer_acc_false[0]
                #     if Flag:
                #         epoch_total_loss+=(step_loss_total+step_loss_total_2)/2
                # # else: 
                        
                    
                    # epoch_total_loss_phase=step_loss_total_phase





                    utils.progress(batch_num,config.batches_per_epoch_train, suffix = 'training done')
                    batch_num+=1


                # epoch_initial_loss = epoch_initial_loss/(config.batches_per_epoch_train *config.batch_size*config.max_phr_len*60)
                epoch_loss_pho = epoch_loss_pho/(config.batches_per_epoch_train*config.batch_size*config.max_phr_len)
                epoch_acc = epoch_acc/(flag_count)
                # epoch_loss_harm = epoch_loss_harm/(config.batches_per_epoch_train *config.batch_size*config.max_phr_len*60)
                # epoch_loss_ap = epoch_loss_ap/(config.batches_per_epoch_train *config.batch_size*config.max_phr_len*4)
                # epoch_loss_f0 = epoch_loss_f0/(config.batches_per_epoch_train*config.batch_size*config.max_phr_len)
                # epoch_acc_f0 = epoch_acc_f0/pho_count

                epoch_loss_f0_midi = epoch_loss_f0_midi/(config.batches_per_epoch_train*config.batch_size*config.max_phr_len)
                epoch_acc_f0_midi = epoch_acc_f0_midi/pho_count

                epoch_loss_singer = epoch_loss_singer/(config.batches_per_epoch_train*config.batch_size)
                epoch_acc_singer = epoch_acc_singer/flag_count

                epoch_total_loss = epoch_total_loss/(config.batches_per_epoch_train*config.batch_size)

                epoch_loss_re_real = epoch_loss_re_real/(config.batches_per_epoch_train*config.batch_size)
                epoch_loss_re_false = epoch_loss_re_false/(config.batches_per_epoch_train*config.batch_size)
                epoch_loss_cg_real = epoch_loss_cg_real/(config.batches_per_epoch_train*config.batch_size)
                epoch_loss_cg_false = epoch_loss_cg_false/(config.batches_per_epoch_train*config.batch_size)
                epoch_acc_real = epoch_acc_real/flag_count
                epoch_acc_false = epoch_acc_false/flag_count

                epoch_dis_loss = epoch_dis_loss/(config.batches_per_epoch_train*config.batch_size)

                # import pdb;pdb.set_trace()
                # epoch_loss_vuv = epoch_loss_vuv/(config.batches_per_epoch_train *config.batch_size*config.max_phr_len)
                # epoch_total_loss = epoch_total_loss/(config.batches_per_epoch_train *config.batch_size)
                # epoch_total_loss_phase = epoch_total_loss_phase/(config.batches_per_epoch_train *config.batch_size)

                # summary_str = sess.run(summary, feed_dict={input_placeholder: featies,  
                #     labels:pho_targs, singer_labels: singer_ids, singer_embedding_placeholder: s_embed, f0_input_placeholder_midi: f0_2_one_hot, f0_target_placeholder_midi: targets_f0_2, pho_input_placeholder:pho_one_hot, 
                #     output_placeholder: feats_targets, prob:0.5, singer_labels_2: singer_ids})
                # # import pdb;pdb.set_trace()
                # train_summary_writer.add_summary(summary_str, epoch)
                # # summary_writer.add_summary(summary_str_val, epoch)
                # train_summary_writer.flush()

            with tf.variable_scope('Validation'):

                for inputs, feats_targets, targets_f0_1, targets_f0_2, pho_targs, singer_ids, Flag in val_generator:

                    f0_1_one_hot = one_hotize(targets_f0_1, max_index=256)

                    f0_2_one_hot = one_hotize(targets_f0_2, max_index=57)

                    pho_one_hot = one_hotize(pho_targs, max_index=42)

                    random_inputs = np.random.rand(config.batch_size, config.max_phr_len, 1)

                    featies = feats_targets

                    step_loss_f0_midi, step_acc_f0_midi = sess.run([f0_loss_midi, f0_acc_midi_val], feed_dict={input_placeholder: featies,f0_target_placeholder_midi: targets_f0_2})
                    step_loss_singer, step_acc_singer, s_embed = sess.run([singer_loss, singer_acc_val, singer_embedding], feed_dict={input_placeholder: featies,singer_labels: singer_ids})

                    

                    # step_loss_f0, step_acc_f0 = sess.run([f0_loss, f0_acc_val], feed_dict={input_placeholder: featies,singer_embedding_placeholder: s_embed, f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder:pho_one_hot, f0_target_placeholder: targets_f0_1})
                    step_loss_pho, step_acc_pho = sess.run([pho_loss, pho_acc_val], feed_dict={input_placeholder: featies,f0_input_placeholder_midi:f0_2_one_hot, labels: pho_targs})
                    step_loss_total = sess.run(reconstruct_loss, feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: f0_2_one_hot, pho_input_placeholder: pho_one_hot, output_placeholder: feats_targets,singer_embedding_placeholder: s_embed})
                    # step_loss_total_phase = sess.run(reconstruct_loss_phase, feed_dict={input_placeholder:inputs, f0_input_placeholder: one_hotize(targets_f0_1, max_index=256), pho_input_placeholder: one_hotize(pho_targs, max_index=41),singer_embedding_placeholder: s_embed, prob:0.5, output_phase_placeholder: phase_targets})


                    epoch_loss_pho_val+=step_loss_pho
                    epoch_acc_val+=step_acc_pho[0]
                    pho_count_val+=1

                    

                    # epoch_loss_f0_val+=step_loss_f0
                    # epoch_acc_f0_val+=step_acc_f0[0]

                    epoch_loss_f0_midi_val+=step_loss_f0_midi
                    epoch_acc_f0_midi_val+=step_acc_f0_midi[0]

                    epoch_loss_singer_val+=step_loss_singer
                    epoch_acc_singer_val+=step_acc_singer[0]
                    epoch_total_loss_val+=step_loss_total
                    # epoch_total_loss_phase_val+=step_loss_total_phase





                    utils.progress(batch_num_val,config.batches_per_epoch_val, suffix = 'validation done')
                    batch_num_val+=1


                # epoch_initial_loss = epoch_initial_loss/(config.batches_per_epoch_train *config.batch_size*config.max_phr_len*60)
                epoch_loss_pho_val = epoch_loss_pho_val/(config.batches_per_epoch_val*config.batch_size*config.max_phr_len)
                epoch_acc_val = epoch_acc_val/(pho_count_val)
                # epoch_loss_harm = epoch_loss_harm/(config.batches_per_epoch_train *config.batch_size*config.max_phr_len*60)
                # epoch_loss_ap = epoch_loss_ap/(config.batches_per_epoch_train *config.batch_size*config.max_phr_len*4)
                # epoch_loss_f0_val = epoch_loss_f0_val/(config.batches_per_epoch_val*config.batch_size*config.max_phr_len)
                # epoch_acc_f0_val = epoch_acc_f0_val/pho_count_val

                epoch_loss_f0_midi_val = epoch_loss_f0_midi_val/(config.batches_per_epoch_val*config.batch_size*config.max_phr_len)
                epoch_acc_f0_midi_val = epoch_acc_f0_midi_val/pho_count_val

                epoch_loss_singer_val = epoch_loss_singer_val/(config.batches_per_epoch_val*config.batch_size)

                epoch_total_loss_val = epoch_total_loss_val/(config.batches_per_epoch_val*config.batch_size)
                epoch_acc_singer_val = epoch_acc_singer_val/pho_count_val
                # epoch_loss_vuv = epoch_loss_vuv/(config.batches_per_epoch_train *config.batch_size*config.max_phr_len)
                # epoch_total_loss_val = epoch_total_loss_val/(config.batches_per_epoch_val *config.batch_size)
                # epoch_total_loss_phase_val = epoch_total_loss_phase_val/(config.batches_per_epoch_val *config.batch_size)

                # summary_str = sess.run(summary_val, feed_dict={input_placeholder: featies,
                #     labels:pho_targs, singer_labels: singer_ids, singer_embedding_placeholder: s_embed, f0_input_placeholder_midi: f0_2_one_hot, f0_target_placeholder_midi: targets_f0_2, pho_input_placeholder:pho_one_hot, 
                #     output_placeholder: feats_targets, prob:0.5})
                # val_summary_writer.add_summary(summary_str, epoch)
                # # summary_writer.add_summary(summary_str_val, epoch)
                # val_summary_writer.flush()

            duration = time.time() - start_time

            # np.save('./ikala_eval/accuracies', f0_accs)

            if (epoch+1) % config.print_every == 0:
                print('epoch %d: F0 Midi Training Loss = %.10f (%.3f sec)' % (epoch+1, epoch_loss_f0_midi, duration))
                # print('        : F0 Training Accuracy = %.10f ' % (epoch_acc_f0))
                # print('        : F0 Midi Training Loss = %.10f ' % (epoch_loss_f0_midi))
                print('        : F0 Midi Accuracy = %.10f ' % (epoch_acc_f0_midi))

                print('        : Pho Training Loss = %.10f ' % (epoch_loss_pho))
                print('        : Pho  Accuracy = %.10f ' % (epoch_acc))

                print('        : Singer Training Loss = %.10f ' % (epoch_loss_singer))
                print('        : Singer  Accuracy = %.10f ' % (epoch_acc_singer))

                print('        : GAN Generator Loss = %.10f ' % (epoch_loss_cg_real ))

                print('        : Reconstrubtion Real = %.10f ' % (epoch_loss_re_real ))

                print('        : Final Loss = %.10f ' % (epoch_total_loss))

                print('        : GAN Discriminator Loss = %.10f ' % (epoch_dis_loss ))
                
                # print('        : Reconstrubtion Loss False = %.10f ' % (epoch_loss_re_false ))
                # print('        : CGAN Loss Real = %.10f ' % (epoch_loss_cg_real))
                # print('        : CGAN Loss Fake = %.10f ' % (epoch_loss_cg_false ))
                # print('        : CGAN Accuracy Real = %.10f ' % (epoch_acc_real))
                # print('        : CGAN Accuracy Fake = %.10f ' % (epoch_acc_false))


                # print('        : Reconstrubtion Loss Phase = %.10f ' % (epoch_total_loss_phase))


                # print('        : Val F0 Training Loss = %.10f' % (epoch_loss_f0_val))
                # print('        : Val F0 Training Accuracy = %.10f ' % (epoch_acc_f0_val))
                print('        : Val F0 Midi Training Loss = %.10f ' % (epoch_loss_f0_midi_val))
                print('        : Val F0 Midi Accuracy = %.10f ' % (epoch_acc_f0_midi_val))

                print('        : Val Pho Training Loss = %.10f ' % (epoch_loss_pho_val))
                print('        : Val Pho  Accuracy = %.10f ' % (epoch_acc_val))

                print('        : Val Singer Training Loss = %.10f ' % (epoch_loss_singer_val))
                print('        : Val Singer  Accuracy = %.10f ' % (epoch_acc_singer_val))
                print('        : Val Reconstrubtion Loss = %.10f ' % (epoch_total_loss_val))

                # import pdb;pdb.set_trace()
                # print('        : Val Reconstrubtion Loss Phase = %.10f ' % (epoch_total_loss_phase_val))



            if (epoch + 1) % config.save_every == 0 or (epoch + 1) == config.num_epochs:
                # utils.list_to_file(val_f0_accs,'./ikala_eval/accuracies_'+str(epoch+1)+'.txt')
                checkpoint_file = os.path.join(config.log_dir, 'model.ckpt')
                saver.save(sess, checkpoint_file, global_step=epoch)


def synth_file(file_path=config.wav_dir, show_plots=True, save_file=True):

    file_name = "nus_VKOW_sing_20.hdf5"



    speaker_file = "nus_VKOW_sing_20.hdf5"

    stat_file = h5py.File(config.stat_dir+'stats.hdf5', mode='r')

    max_feat = np.array(stat_file["feats_maximus"])
    min_feat = np.array(stat_file["feats_minimus"])
    max_voc = np.array(stat_file["voc_stft_maximus"])
    min_voc = np.array(stat_file["voc_stft_minimus"])
    max_back = np.array(stat_file["back_stft_maximus"])
    min_back = np.array(stat_file["back_stft_minimus"])
    max_mix = np.array(max_voc)+np.array(max_back)

    with tf.Graph().as_default():

        speaker_input_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,66),name='speaker_input_placeholder')

        
        input_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,66),name='input_placeholder')
        tf.summary.histogram('inputs', input_placeholder)

        output_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,66),name='output_placeholder')

        rand_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,1),name='random_placeholder')

        # output_phase_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len,config.input_features),name='output_phase_placeholder')

        f0_target_placeholder_midi = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len),name='f0_target_midi_placeholder')
        onehot_labels_f0_midi = tf.one_hot(indices=tf.cast(f0_target_placeholder_midi, tf.int32), depth=57)

        f0_input_placeholder_midi = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len, 57),name='f0_input_placeholder')

        # f0_target_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len),name='f0_target_placeholder')
        # onehot_labels_f0 = tf.one_hot(indices=tf.cast(f0_target_placeholder, tf.int32), depth=256)

        # f0_input_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len, 256),name='f0_input_placeholder')

        pho_input_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,config.max_phr_len, 42),name='pho_input_placeholder')

        prob = tf.placeholder_with_default(1.0, shape=())

        # tf.summary.histogram('targets', target_placeholder)
        
        labels = tf.placeholder(tf.int32, shape=(config.batch_size,config.max_phr_len),name='phoneme_placeholder')
        onehot_labels = tf.one_hot(indices=tf.cast(labels, tf.int32), depth=42)

        singer_labels = tf.placeholder(tf.int32, shape=(config.batch_size),name='singer_id_placeholder')
        onehot_labels_singer = tf.one_hot(indices=tf.cast(singer_labels, tf.int32), depth=121)

        singer_labels_2 = tf.placeholder(tf.int32, shape=(config.batch_size),name='singer_id_placeholder_2')
        onehot_labels_singer_2 = tf.one_hot(indices=tf.cast(singer_labels_2, tf.int32), depth=121)

        singer_embedding_placeholder = tf.placeholder(tf.float32, shape=(config.batch_size,256),name='singer_embedding_placeholder')





        with tf.variable_scope('F0_Model_midi') as scope:
            f0_logits_midi = modules.f0_network(input_placeholder, prob)
            f0_classes_midi = tf.argmax(f0_logits_midi, axis=-1)
            f0_probs_midi = tf.nn.softmax(f0_logits_midi)

        # with tf.variable_scope('F0_Model_256') as scope:
        #     f0_logits = modules.f0_network_2(singer_embedding_placeholder, f0_input_placeholder_midi, pho_input_placeholder, prob)
        #     f0_classes = tf.argmax(f0_logits, axis=-1)
        #     f0_probs = tf.nn.softmax(f0_logits)

        with tf.variable_scope('Final_Model') as scope:
            voc_output = modules.final_net(rand_placeholder, singer_embedding_placeholder, f0_input_placeholder_midi, pho_input_placeholder, prob)
            voc_output_decoded = tf.nn.sigmoid(voc_output)

        # with tf.variable_scope('Final_Model_Phase') as scope:
        #     voc_output_phase = modules.final_net_phase(singer_embedding_placeholder, f0_input_placeholder, pho_input_placeholder, input_placeholder, prob)
        #     voc_output_phase_decoded = tf.nn.sigmoid(voc_output_phase)

        with tf.variable_scope('phone_Model') as scope:
            regularizer = tf.contrib.layers.l2_regularizer(scale=0.1)
            pho_logits = modules.phone_network(input_placeholder, prob, regularizer = regularizer)
            pho_classes = tf.argmax(pho_logits, axis=-1)
            pho_probs = tf.nn.softmax(pho_logits)

        with tf.variable_scope('singer_Model') as scope:
            singer_embedding, singer_logits = modules.singer_network(speaker_input_placeholder, prob)
            singer_classes = tf.argmax(singer_logits, axis=-1)
            singer_probs = tf.nn.softmax(singer_logits)
        # with tf.variable_scope('Final_Model_Phase') as scope:
        #     voc_output_phase = modules.final_net_phase(singer_embedding_placeholder, f0_input_placeholder, pho_input_placeholder, input_placeholder, prob)
        #     voc_output_phase_decoded = tf.nn.sigmoid(voc_output_phase)


        saver = tf.train.Saver(max_to_keep= config.max_models_to_keep)


        init_op = tf.group(tf.global_variables_initializer(), tf.local_variables_initializer())
        sess = tf.Session()

        sess.run(init_op)

        ckpt = tf.train.get_checkpoint_state(config.log_dir)

        if ckpt and ckpt.model_checkpoint_path:
            print("Using the model in %s"%ckpt.model_checkpoint_path)
            saver.restore(sess, ckpt.model_checkpoint_path)
            # saver.restore(sess, './log_feat_to_feat_sim_cgan_2/model.ckpt-139')

        # import pdb;pdb.set_trace()





        voc_file = h5py.File(config.voice_dir+file_name, "r")

        speaker_file = h5py.File(config.voice_dir+speaker_file, "r")

        voc_stft = np.array(voc_file['voc_stft'])

        # voc_stft = utils.file_to_stft('./billy.wav', mode =1)

        speaker_stft = np.array(speaker_file['voc_stft'])
        # speaker_stft = utils.file_to_stft('./bellaciao.wav', mode =1)

        speaker_stft = np.repeat(speaker_stft, int(np.ceil(voc_stft.shape[0]/speaker_stft.shape[0])),0)

        speaker_stft = speaker_stft[:voc_stft.shape[0]]

        # voc_file.close()

        # speaker_file.close()
        # import pdb;pdb.set_trace()

        feats = np.array(voc_file['feats'])

        # feats = utils.input_to_feats('./franky.wav', mode = 1)

        

        # feats = utils.input_to_feats('./billy.wav', mode = 1)

        f0 = feats[:,-2]

        # import pdb;pdb.set_trace()

        med = np.median(f0[f0 > 0])

        f0[f0==0] = med

        # import pdb;pdb.set_trace()

        f0_midi = np.rint(f0) - 30

        f0_nor = (f0 - min_feat[-2])/(max_feat[-2]-min_feat[-2])

        f0_quant = np.rint(f0_nor*176) + 1

        f0_quant = f0_quant * (1-feats[:,-1]) 

        f0_midi = f0_midi * (1-feats[:,-1]) 

        featies = feats



        speaker_feats = np.array(speaker_file['feats'])

        # speaker_feats = utils.input_to_feats('./franky.wav', mode = 1)

        speaker_f0 = speaker_feats[:,-2]

        # import pdb;pdb.set_trace()

        med = np.median(speaker_f0[speaker_f0 > 0])

        speaker_f0[speaker_f0==0] = med

        # import pdb;pdb.set_trace()

        speaker_f0_nor = (speaker_f0 - min_feat[-2])/(max_feat[-2]-min_feat[-2])

        speaker_f0_quant = np.rint(speaker_f0_nor*176) + 1

        speaker_f0_quant = speaker_f0_quant * (1-speaker_feats[:,-1]) 

        # import pdb;pdb.set_trace()

        # speaker_featies = np.concatenate(((np.array(speaker_feats[:,:-2])-min_feat[:-2])/(max_feat[:-2]-min_feat[:-2]), (speaker_f0_quant/256.0).reshape(-1 , 1)), axis = -1)
        
        speaker_featies = (np.array(speaker_feats)-min_feat)/(max_feat-min_feat)

        speaker_featies = np.repeat(speaker_featies, int(np.ceil(featies.shape[0]/speaker_featies.shape[0])),0)

        speaker_featies = speaker_featies[:featies.shape[0]]
        

        pho_target = np.array(voc_file["phonemes"])




        in_batches_voc_stft, nchunks_in = utils.generate_overlapadd(voc_stft)

        in_batches_speaker_feats, nchunks_in_speaker = utils.generate_overlapadd(speaker_featies)

        # import pdb;pdb.set_trace()

        in_batches_f0_midi, nchunks_in = utils.generate_overlapadd(f0_midi.reshape(-1,1))

        # in_batches_f0_quant, nchunks_in = utils.generate_overlapadd(f0_quant.reshape(-1,1))

        in_batches_pho, nchunks_in_pho = utils.generate_overlapadd(pho_target.reshape(-1,1))

        in_batches_feat, kaka = utils.generate_overlapadd(featies)

        # import pdb;pdb.set_trace()




        out_batches_feats = []

        out_batches_voc_stft_phase = []

        out_batches_f0_midi = []

        out_batches_f0_quant = []

        out_batches_pho_target = []

        out_embeddings = []

        # voc_stft_mag, voc_stft_phase = utils.file_to_stft(config.wav_dir_nus+'KENN/sing/04.wav', mode = 3)

        for in_batch_speaker_stft in in_batches_speaker_feats:
            s_embed = sess.run(singer_embedding, feed_dict={speaker_input_placeholder: in_batch_speaker_stft})
            out_embeddings.append(s_embed)
        out_embeddings = np.array(out_embeddings)
        s_embed = np.tile(np.mean(np.mean(out_embeddings, axis = 0), axis = 0), (config.batch_size,1))

        # import pdb;pdb.set_trace()



        for in_batch_voc_stft, in_batch_f0_midi,  in_batch_pho_target, in_batch_speaker_feat, in_batch_feat  in zip(in_batches_voc_stft, in_batches_f0_midi, in_batches_pho, in_batches_speaker_feats, in_batches_feat):
        # for in_batch_voc_stft, in_batch_f0_midi, in_batch_f0_quant in zip(in_batches_voc_stft, in_batches_f0_midi, in_batches_f0_quant):

            # in_batch_voc_stft = in_batch_voc_stft/(in_batch_voc_stft.max(axis = 1).max(axis = 0))
            # in_batch_speaker_stft = in_batch_speaker_stft/(in_batch_speaker_stft.max(axis = 1).max(axis = 0))
            # in_batch_voc_stft = in_batch_voc_stft/max_voc
            # in_batch_speaker_stft = in_batch_speaker_stft/max_voc



            # s_embed = sess.run(singer_embedding, feed_dict={speaker_input_placeholder: in_batch_speaker_feat})



            # import pdb;pdb.set_trace()

            f0_outputs_1 = sess.run(f0_probs_midi, feed_dict = {input_placeholder: in_batch_feat,singer_embedding_placeholder: s_embed} )

            # in_batch_voc_stft = in_batch_voc_stft.reshape([config.batch_size, config.max_phr_len, 256])

            # in_batch_f0_quant = in_batch_f0_quant.reshape([config.batch_size, config.max_phr_len])

            in_batch_f0_midi = in_batch_f0_midi.reshape([config.batch_size, config.max_phr_len])

            in_batch_pho_target = in_batch_pho_target.reshape([config.batch_size, config.max_phr_len])

            random_inputs = np.random.rand(config.batch_size, config.max_phr_len, 1)




            pho_outs = sess.run(pho_probs, feed_dict = {input_placeholder: in_batch_feat,f0_input_placeholder_midi: one_hotize(in_batch_f0_midi, max_index=57)} )

            # f0_outputs_2 = sess.run(f0_probs, feed_dict={singer_embedding_placeholder: s_embed, 
            #     f0_input_placeholder_midi: one_hotize(in_batch_f0_midi, max_index=57), pho_input_placeholder: one_hotize(in_batch_pho_target, max_index=42)} )

            # output_voc_stft = sess.run(voc_output_decoded, feed_dict={f0_input_placeholder: one_hotize(in_batch_f0_quant, max_index=256),
            #     pho_input_placeholder: one_hotize(in_batch_pho_target, max_index=41), output_placeholder: in_batch_voc_stft,singer_embedding_placeholder: s_embed})


            output_feats = sess.run(voc_output_decoded, feed_dict={rand_placeholder:random_inputs,f0_input_placeholder_midi: one_hotize(in_batch_f0_midi, max_index=57),
                pho_input_placeholder: one_hotize(in_batch_pho_target, max_index=42),singer_embedding_placeholder: s_embed})

            # output_voc_stft_phase = sess.run(voc_output_phase_decoded, feed_dict={input_placeholder: output_voc_stft, f0_input_placeholder: f0_outputs_2,
            #     pho_input_placeholder: one_hotize(in_batch_pho_target, max_index=41), output_placeholder: in_batch_voc_stft,singer_embedding_placeholder: s_embed})

                # f0_input_placeholder: one_hotize(in_batch_f0_quant, max_index=256),pho_input_placeholder: one_hotize(in_batch_pho_target, max_index=41), output_placeholder: in_batch_voc_stft,singer_embedding_placeholder: s_embed})

            out_batches_feats.append(output_feats)

            out_batches_f0_midi.append(f0_outputs_1)

            # out_batches_f0_quant.append(f0_outputs_2)

            out_batches_pho_target.append(pho_outs)

            # out_batches_voc_stft_phase.append(output_voc_stft_phase)



        # import pdb;pdb.set_trace()

        out_batches_feats = np.array(out_batches_feats)
        # import pdb;pdb.set_trace()
        out_batches_feats = utils.overlapadd(out_batches_feats, nchunks_in) 

        

        # out_batches_voc_stft_phase = np.array(out_batches_voc_stft_phase)
        # # import pdb;pdb.set_trace()
        # out_batches_voc_stft_phase = utils.overlapadd(out_batches_voc_stft_phase, nchunks_in) 

        out_batches_f0_midi = np.array(out_batches_f0_midi)
        out_batches_f0_midi = utils.overlapadd(out_batches_f0_midi, nchunks_in)    

        # out_batches_f0_quant = np.array(out_batches_f0_quant)
        # out_batches_f0_quant = utils.overlapadd(out_batches_f0_quant, nchunks_in) 

        # f0_output= np.argmax(out_batches_f0_quant, axis = -1).astype('float32')
        # f0_output[f0_output == 0] = np.nan

        # f0_output = (f0_output - 1)/255

        # f0_output = f0_output*(max_feat[-2]-min_feat[-2]) + min_feat[-2]
        # f0_output = np.nan_to_num(f0_output)

        out_batches_feats = out_batches_feats*(max_feat-min_feat)+min_feat


        # haha = np.concatenate((out_batches_feats[:f0.shape[0]], feats[:,-2:-1], feats[:,-1:]) ,axis=-1)
        haha = out_batches_feats[:f0.shape[0]]
        # import pdb;pdb.set_trace()
        haha[:,-2:] = feats[:,-2:]

        haha[:,-2] = haha[:,-2]
        # import pdb;pdb.set_trace()
        haha = np.ascontiguousarray(haha)

        # jaja = np.concatenate((out_batches_feats[:f0.shape[0]], f0_output[:f0.shape[0]].reshape(-1,1)) ,axis=-1)

        # # import pdb;pdb.set_trace()

        # jaja = np.concatenate((jaja,feats[:,-1:]) ,axis=-1)


        
        # jaja = np.ascontiguousarray(jaja)

        # hehe = np.concatenate((out_batches_feats[:f0.shape[0],:60], feats[:,60:]) ,axis=-1)
        # hehe = np.ascontiguousarray(hehe)

        # import pdb;pdb.set_trace()




        # import pdb;pdb.set_trace()


        plt.figure(1)

        plt.subplot(211)

        plt.imshow(feats[:,:60].T,aspect='auto',origin='lower')

        plt.subplot(212)

        plt.imshow(out_batches_feats[:,:60].T,aspect='auto',origin='lower')


        plt.figure(2)

        plt.subplot(211)

        plt.imshow(feats[:,60:-2].T,aspect='auto',origin='lower')

        plt.subplot(212)

        plt.imshow(out_batches_feats[:,60:-2].T,aspect='auto',origin='lower')

        plt.figure(3)
        plt.plot(((feats[:,-2:-1]*(1-feats[:,-1:]))-69+(12*np.log2(440))-(12*np.log2(10)))*100)
        plt.plot(((out_batches_feats[:,-2:-1]*(1-out_batches_feats[:,-1:])) -69+(12*np.log2(440))-(12*np.log2(10)))*100)

        utils.feats_to_audio(haha[:5000,:],'VKOW_20_From_VKOW_20.wav')


        # plt.plot(f0_output)

        plt.show()

        import pdb;pdb.set_trace()

        # utils.feats_to_audio(jaja[:5000,:],'_test_ADIZ_01_SAMF.wav')

        # utils.feats_to_audio(hehe[:5000,:],'_test_with_original_f0_ap.wav')

        # utils.feats_to_audio(feats[:5000,:],'_test_original.wav')




        # utils.feats_to_audio(feats,'_synth_ori_f0')



        import pdb;pdb.set_trace()

        out_batches_pho_target = np.array(out_batches_pho_target)
        out_batches_pho_target = utils.overlapadd(out_batches_pho_target, nchunks_in)   

        pho_target_oh = one_hotize(pho_target, max_index=42)

        f0_midi_oh = one_hotize(f0_midi, max_index=54)

        f0_quant_oh = one_hotize(f0_quant, max_index=256)

        out_batches_voc_stft = out_batches_voc_stft[:voc_stft.shape[0],:]*max_voc

        out_batches_voc_stft_phase = (out_batches_voc_stft_phase[:voc_stft.shape[0],:]*(3.1415927*2))-3.1415927

        # import pdb;pdb.set_trace()

        audio_out = utils.istft(out_batches_voc_stft, voc_stft_phase[:out_batches_voc_stft.shape[0],:])

        audio_out_out_phase = utils.istft(out_batches_voc_stft, out_batches_voc_stft_phase)

        # audio_out_1 = utils.griffin_lim(out_batches_voc_stft, audio_out.shape )

        audio_out_griffin = audio_utilities.reconstruct_signal_griffin_lim(out_batches_voc_stft, 1024, 256, 100)

        audio_out_griffin_test = audio_utilities.reconstruct_signal_griffin_lim(voc_stft_mag, 1024, 256, 100)

        

        sf.write('./test_ori_pha.wav',audio_out,config.fs)

        sf.write('./test_griffin.wav',audio_out_griffin,config.fs)

        sf.write('./test_griffin_test.wav',audio_out_griffin_test,config.fs)

        sf.write('./test_out_phase.wav',audio_out_out_phase,config.fs)

        import pdb;pdb.set_trace() 
        

        if show_plots:

            plt.figure(1)
            ax1 = plt.subplot(211)
            plt.imshow(np.log(voc_stft.T), origin='lower', aspect='auto')
            ax1.set_title("Ground Truth FFT", fontsize = 10)
            ax2 = plt.subplot(212)
            plt.imshow(np.log(out_batches_voc_stft.T), origin='lower', aspect='auto')
            ax2.set_title("Synthesized FFT ", fontsize = 10)

            plt.figure(2)
            ax1 = plt.subplot(211)
            plt.imshow(pho_target_oh.T, origin='lower', aspect='auto')
            ax1.set_title("Ground Truth Phonemes", fontsize = 10)
            ax2 = plt.subplot(212)
            plt.imshow(out_batches_pho_target.T, origin='lower', aspect='auto')
            ax2.set_title("Predicted PPGs", fontsize = 10)

            plt.figure(3)
            ax1 = plt.subplot(211)
            plt.imshow(f0_midi_oh.T, origin='lower', aspect='auto')
            ax1.set_title("Ground Truth Midi Notes", fontsize = 10)
            ax2 = plt.subplot(212)
            plt.imshow(out_batches_f0_midi.T, origin='lower', aspect='auto')
            ax2.set_title("Predicted Midi Notes", fontsize = 10)
                
            plt.figure(4)
            ax1 = plt.subplot(211)
            plt.imshow(f0_quant_oh.T, origin='lower', aspect='auto')
            ax1.set_title("Ground Truth F0 In Cents (quantized to 256 bins, 30 cents each)", fontsize = 10)
            ax2 = plt.subplot(212)
            plt.imshow(out_batches_f0_quant.T, origin='lower', aspect='auto')
            ax2.set_title("Predicted F0 In Cents", fontsize = 10)

            plt.figure(5)
            f0_midi_oh_hh = np.argmax(f0_midi_oh, axis = -1).astype('float32')
            f0_midi_oh_hh[f0_midi_oh_hh == 0] = np.nan

            f0_midi_oh_hb = np.argmax(out_batches_f0_midi, axis = -1).astype('float32')
            f0_midi_oh_hb[f0_midi_oh_hb == 0] = np.nan


            plt.plot(f0_midi_oh_hh, label = "Ground Truth Midi Note")
            plt.plot(f0_midi_oh_hb, label = "Predicted Midi Note")
            plt.legend()

            plt.figure(6)
            f0_midi_oh_hh = np.argmax(f0_quant_oh, axis = -1).astype('float32')
            f0_midi_oh_hh[f0_midi_oh_hh == 0] = np.nan

            f0_midi_oh_hb = np.argmax(out_batches_f0_quant, axis = -1).astype('float32')
            f0_midi_oh_hb[f0_midi_oh_hb == 0] = np.nan


            plt.plot(f0_midi_oh_hh, label = "Ground Truth F0 in Cents")
            plt.plot(f0_midi_oh_hb, label = "Predicted F0 in Cents")

            plt.legend()

            plt.show()




if __name__ == '__main__':
    if sys.argv[1] == '-train' or sys.argv[1] == '--train' or sys.argv[1] == '--t' or sys.argv[1] == '-t':
        print("Training")
        tf.app.run(main=train)
    elif sys.argv[1] == '-synth' or sys.argv[1] == '--synth' or sys.argv[1] == '--s' or sys.argv[1] == '-s':
        synth_file()




