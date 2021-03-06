#!/usr/bin/env python
# Filename: image_classify_rnn 
"""
introduction: classification multi-spectral remote sensing images using RNN. This is pixel-based classification

using tensorflow to implement this ideas

authors: Huang Lingcao
email:huanglingcao@gmail.com
add time: 10 April, 2018
"""


import sys,os
from optparse import OptionParser

import numpy as np
import random
import rasterio


###-------------------------- set gpu using tf ---------------------------
import tensorflow as tf
config = tf.ConfigProto()
config.gpu_options.allow_growth = True
session = tf.Session(config=config)
###-------------------  start importing keras module ---------------------


import matplotlib.pyplot as plt
import datetime
import time

import sklearn

#we only have 20 classes, however, class index start from 1, so use 21. We should ignore the "0" class in the end
num_classes = 21
learn_rate = 0.001
hidden_units = 128
batch_size =  2048 #256 2048
lstm_layer_num = 5

epoches = 200

def read_oneband_image_to_1dArray(image_path):

    if os.path.isfile(image_path) is False:
        print("error, file not exist: " + image_path)
        return None

    with rasterio.open(image_path) as img_obj:
        # read the all bands (only have one band)
        indexes = img_obj.indexes
        if len(indexes) != 1:
            print('error, only support one band')
            return None

        data = img_obj.read(indexes)

        data_1d = data.flatten()  # convert to one 1d, row first.

        return data_1d


def read_multiband_image_to_2dArray(image_path):
    """

    :param image_path:
    :return: 2d Array (bands, number of pixels)
    """

    if os.path.isfile(image_path) is False:
        print("error, file not exist: " + image_path)
        return None

    with rasterio.open(image_path) as img_obj:
        # read the all bands (only have one band)
        indexes = img_obj.indexes

        data = img_obj.read(indexes)
        band,height, width = data.shape
        # print(data.shape)
        data = np.transpose(data,(1,2,0))  # this is necessary before reshape, or the arrary is wrong
        data_2d = data.reshape(height*width,band)  # row first
        return data_2d

def split_data(x_all, y_all, test_percent=0.01):
    """
    split the data to train set and test set
    :param x_all: all the x : (count,n_features)
    :param y_all: all the y : (count,1)
    :param percent: the percent of the test set [0,1]
    :return: (x_train, y_train), (x_test, y_test)
    """

    total_count = x_all.shape[0]
    test_count = int(total_count*test_percent)

    # random select the test sample
    # bug: np.random.randint could output some duplicated number, which causes not consist amount when using np.delete
    # test_index = np.random.randint(0,total_count,size=test_count)
    test_index = random.sample(range(total_count), test_count)
    # test_index = np.array(range(0,test_count))
    # test_index = sorted(test_index)

    x_test = x_all[test_index]
    y_test = y_all[test_index]
    # print(len(test_index), min(test_index),max(test_index),'size, minimum, and maximum of of test_index')

    x_train = np.delete(x_all,test_index,axis=0)
    y_train = np.delete(y_all,test_index,axis=0)

    # print(x_all.shape[0], 'total count before splitting')
    # print(x_train.shape[0]+x_test.shape[0],'total count after splitting')
    #
    # print(x_train.shape[0],y_train.shape[0], 'train samples (x,y)')
    # print(x_test.shape[0],y_test.shape[0], 'test samples (x,y)')

    return (x_train, y_train), (x_test, y_test)

# def build_train_rnn_model(x_shape):
#
#     model = tf.keras.models.Sequential()
#     # model.add(LSTM(hidden_units, input_shape=x_shape))
#     model.add(tf.keras.layers.LSTM(hidden_units,input_shape=x_shape,return_sequences=True)) #,return_sequences=True
#
#     model.add(tf.keras.layers.LSTM(hidden_units, return_sequences=True))
#     model.add(tf.keras.layers.LSTM(hidden_units, return_sequences=True))
#     model.add(tf.keras.layers.LSTM(hidden_units, return_sequences=True))
#
#     model.add(tf.keras.layers.LSTM(hidden_units))
#
#     model.add(tf.keras.layers.Dense(num_classes, activation='softmax'))
#
#     # complie model
#     model.compile(loss='categorical_crossentropy',optimizer='rmsprop',metrics=['accuracy'])
#
#     return model

def lstm_layer(hidden_units,keep_prob):
    """
    setting a lstm layer
    :param hidden_units: the number of hidden units in this layer
    :param keep_prob: the dropout parameters, i.e. how many percent want to keep
    :return: this layer
    """

    layer = tf.contrib.rnn.BasicLSTMCell(hidden_units)
    # layer = tf.contrib.rnn.LSTMCell(hidden_units)

    # dropout, only apply to the output units
    cell = tf.contrib.rnn.DropoutWrapper(layer, input_keep_prob=keep_prob,output_keep_prob=keep_prob, state_keep_prob=keep_prob)
    return layer

def multi_lstm_layers(hidden_units,keep_prob,layer_num):

    mlstm_cell = tf.contrib.rnn.MultiRNNCell([lstm_layer(hidden_units, keep_prob) for _ in range(layer_num)],
                                             state_is_tuple=True)
    return mlstm_cell


def inference(image_path,train_log_folder,save_path):
    """
    inference 
    :param image_path: the image for inference 
    :param train_log_folder:  the folder containing meta and checkpoint file
    :return: 
    """
    # get the lastest tensorflow file
    saver = tf.train.import_meta_graph(os.path.join(train_log_folder,'hyperRNN-177600.meta'))
    saver.restore(session,tf.train.latest_checkpoint(train_log_folder))

    # read the image
    multiBand_value_2d = read_multiband_image_to_2dArray(image_path)
    if multiBand_value_2d is None:
        return False
    x_inf_input = multiBand_value_2d.reshape(multiBand_value_2d.shape[0], multiBand_value_2d.shape[1], 1)

    print(x_inf_input.shape[0], x_inf_input.shape[0], 'train samples')
    x_inf_input = x_inf_input.astype('float32')
    x_inf_input /= 65536
    band_num = x_inf_input.shape[1]
    input_sample_num = x_inf_input.shape[0]

    # inference
    X_input = tf.get_default_graph().get_tensor_by_name('xInput:0')
    batch_size_v = tf.get_default_graph().get_tensor_by_name('batch_size_v:0')
    # keep_prob_v = tf.get_default_graph().get_tensor_by_name('Placeholder:0')  # this should be the name of keep_prob_v
    # keep_prob_v = tf.get_default_graph().get_tensor_by_name('keep_prob_v:0')  # it seems that dropout don't have a effect
    # keep_prob_v: 1.0
    y_pre = tf.get_default_graph().get_tensor_by_name('prediction/class_output:0')

    # session.run(tf.global_variables_initializer())  #bug, we should not call this one

    # f_obj = open('node_name.txt','w')
    # for node in tf.get_default_graph().as_graph_def().node:
    #     # print(node)
    #     print(node.name)
    #     f_obj.write(node.name+'\n')
    #
    # f_obj.close()

    class_output = []

    batch_num = input_sample_num / batch_size
    batch_last_size = input_sample_num % batch_size
    if batch_last_size > 0:
        batch_num += 1
    # train
    for iter in range(batch_num):
        temp_batch_size = batch_size
        if iter == batch_num - 1:
            temp_batch_size = batch_last_size
            X_batch = x_inf_input[iter * batch_size:]
            # y_batch = x_inf_input[iter * batch_size:]
            # continue
            # print(X_batch.shape,y_batch.shape)
        else:
            X_batch = x_inf_input[iter * batch_size:(iter + 1) * batch_size]
            # y_batch = x_inf_input[iter * batch_size:(iter + 1) * batch_size]
            # print(X_batch.shape, y_batch.shape)

        #y_pre_out, x, batch_size_out,keep_prob_out = session.run([y_pre, X_input,batch_size_v,keep_prob_v],
        #feed_dict={X_input: X_batch,batch_size_v:temp_batch_size,keep_prob_v:1.0})

        y_pre_out, x, batch_size_out = session.run([y_pre, X_input,batch_size_v],
        feed_dict={X_input: X_batch,batch_size_v:temp_batch_size})

        # print("keep_prob_out:",keep_prob_out)

        # class_output.append(np.argmax(y_pre_out, 1)[0])
        class_output.extend(np.argmax(y_pre_out, 1))
        # print(list(np.argmax(y_pre_out, 1)))
        print('inference on %d / %d' % (iter + 1, batch_num))

        # sys.exit(0)

    # for idx,sample in enumerate(x_inf_input):
    #     # if idx > 5:
    #     #     break
    #     if idx%1000 ==0:
    #         print('inference on %d / %d'%(idx+1, input_sample_num))
    #     # print(idx,sample)
    #     sample = sample.reshape(1,sample.shape[0],sample.shape[1]) # reshape, batch size is 1, however, batchSize=1 is too slow
    #     y_pre_out, x = session.run([y_pre,X_input],feed_dict={X_input:sample})
    #
    #     # print(x)
    #     # print(y_pre_out)
    #     # print(tf.argmax(y_pre_out,1))
    #     # print(np.argmax(y_pre_out,1))  #output the maximum class number
    #     class_output.append(np.argmax(y_pre_out,1)[0])

    # print(class_output)

    # save results
    with rasterio.open(image_path) as img_obj:
        # read the all bands (only have one band)
        # indexes = img_obj.indexes
        profile = img_obj.profile
        width = img_obj.width
        height = img_obj.height

        class_output_save = np.asarray(class_output)
        class_output_save = class_output_save.reshape(height,width)
        profile.update(dtype=rasterio.uint8,count=1)
        with rasterio.open(save_path, "w", **profile) as dst:
            dst.write(class_output_save.astype(rasterio.uint8), 1)
            print('save result in %s'%save_path)


    pass

def main(options, args):

    t0 = time.time()

    label_image = args[0]
    multi_spec_image_path = args[1]

    # read images
    label_1d = read_oneband_image_to_1dArray(label_image)
    multiBand_value_2d = read_multiband_image_to_2dArray(multi_spec_image_path)

    pixel_count = label_1d.shape[0]
    print(label_1d.shape,multiBand_value_2d.shape)

    # print ten pixels for checking
    # for i in range(10):
    #     index = random.randint(1,label_1d.shape[0])
    #     row = index/2384    # 2384 is the width of the input image
    #     col = index%2384
    #     print("row: %d, col: %d, label: %d"%(row,col,label_1d[index]))
    #     print("pixel value: "+ str(multiBand_value_2d[index]))

    # remove the non-ground truth pixels, that is "0" pixel
    back_ground_index = np.where(label_1d==0)
    label_1d = np.delete(label_1d,back_ground_index)
    multiBand_value_2d = np.delete(multiBand_value_2d, back_ground_index,axis=0)

    print("%.2f %% are unclassified (no observation)"%(len(back_ground_index[0])*100.0/pixel_count))
    print('after removing non-ground truth pixels',label_1d.shape, multiBand_value_2d.shape)

    # split train and test dataset
    (x_train, y_train), (x_test, y_test) = split_data(multiBand_value_2d, label_1d, test_percent=0.1)

    x_train = x_train.reshape(x_train.shape[0],x_train.shape[1],1)
    x_test = x_test.reshape(x_test.shape[0], x_test.shape[1], 1)

    y_train = tf.keras.utils.to_categorical(y_train,num_classes)
    y_test = tf.keras.utils.to_categorical(y_test,num_classes)

    print('x_train shape:', x_train.shape)
    print(x_train.shape[0],y_train.shape[0], 'train samples')
    print(x_test.shape[0],x_test.shape[0], 'test samples')

    train_samples_num = x_train.shape[0]
    test_samples_num = x_test.shape[0]

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')

    # the original data is UINT16, the maximum value is around 45048 for this dataset, but use the simple way here
    x_train /= 65536
    x_test /= 65536

    # bands is the same as feature number of this multi-spectral images
    bands = list(x_train.shape[1:])
    band_num = x_train.shape[1]

    ## start tensorflow codes here
    X_input = tf.placeholder(tf.float32, [None, band_num,1],name='xInput')
    # X_input = tf.reshape(X_input,[-1,band_num,1])
    y_input = tf.placeholder(tf.float32, [None, num_classes],name='yInput')

    # batch size can be changed during the last step in one epoch
    batch_size_v = tf.placeholder(tf.int32, [],name='batch_size_v')
    keep_prob_v = tf.placeholder(tf.float32, [],name='keep_prob_v')   # keep_prob_v is different when training and prediction

    mulit_lstm = multi_lstm_layers(hidden_units,keep_prob_v,lstm_layer_num)

    # init_state = mulit_lstm.zero_state(batch_size_v, dtype=tf.float32)


    # outputs = []
    # state = init_state
    # with tf.variable_scope('RNN'):`
    #     for step in range(band_num):
    #         (cell_output, state) = mulit_lstm(X_input[:, step,:], state)
    #         outputs.append(cell_output)
    # h_state = outputs[-1]

    # outputs, state = tf.nn.dynamic_rnn(mulit_lstm, inputs=X_input, time_major=False,dtype=tf.float32) #initial_state=init_state,

    x = tf.unstack(X_input, band_num, 1)
    # print(x)
    outputs, state = tf.nn.static_rnn(mulit_lstm, x, dtype=tf.float32)
    # h_state = state[-1][1]
    h_state = outputs[-1]


    # weight and bias
    W = tf.Variable(tf.truncated_normal([hidden_units, num_classes], stddev=0.1), dtype=tf.float32)
    bias = tf.Variable(tf.constant(0.1, shape=[num_classes]), dtype=tf.float32)
    # W = tf.Variable(tf.random_normal([hidden_units, num_classes]))
    # bias = tf.Variable(tf.random_normal([num_classes]))
    # y_pre = tf.nn.softmax(tf.matmul(h_state, W) + bias)
    # #it seems that we have two softmax layer (softmax and softmax_cross_entropy_with_logits), make the loss don't decrease
    #
    with tf.variable_scope('prediction'):
        y_pre = tf.add(tf.matmul(h_state, W), bias,name='class_output')


    # loss and evaluation
    # cross_entropy = -tf.reduce_mean(y_input*tf.log(y_pre))
    cross_entropy = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=y_pre,labels=y_input))
    # train_op = tf.train.AdadeltaOptimizer(learning_rate=learn_rate).minimize(cross_entropy)
    train_op = tf.train.RMSPropOptimizer(learning_rate=learn_rate).minimize(cross_entropy)

    correct_pre = tf.equal(tf.argmax(y_pre,1),tf.argmax(y_input,1))
    accuracy = tf.reduce_mean(tf.cast(correct_pre,tf.float32))

    session.run(tf.global_variables_initializer())

    history = {'loss':[],'val_loss':[],'acc':[],'val_acc':[]}

    datetime_str = datetime.datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
    f_obj = open("%s_loss.txt"%datetime_str,"w")

    # save the model to the disk, only keep the last three snapshot
    saver = tf.train.Saver(max_to_keep=3)

    for epoch in range(epoches):
        t_epoch = time.time()
        train_loss = 0.0
        train_acc = 0.0
        val_loss = 0.0
        val_acc = 0.0

        #shuffle train data
        x_train,y_train = sklearn.utils.shuffle(x_train,y_train)

        batch_num = train_samples_num/batch_size
        batch_last_size = train_samples_num%batch_size
        if batch_last_size>0:
            batch_num += 1
        # train
        for iter in range(batch_num):
            temp_batch_size = batch_size
            if iter== batch_num-1:
                temp_batch_size = batch_last_size
                X_batch = x_train[iter*batch_size:]
                y_batch = y_train[iter*batch_size:]
                # continue
                # print(X_batch.shape,y_batch.shape)
            else:
                X_batch = x_train[iter*batch_size:(iter+1)*batch_size]
                y_batch = y_train[iter*batch_size:(iter+1)*batch_size]
                # print(X_batch.shape, y_batch.shape)

            cost, acc, _ = session.run([cross_entropy, accuracy, train_op],
                                feed_dict={X_input: X_batch, y_input: y_batch, keep_prob_v: 0.5, batch_size_v: temp_batch_size})
            train_loss += cost
            train_acc += acc
            print("iter {}, train loss={:.6f}, acc={:.6f}".format(iter+1,cost,acc))

        train_loss /= batch_num
        train_acc /= batch_num
        # test
        X_batch, y_batch = x_test,y_test

        _cost, _acc = session.run([cross_entropy, accuracy],
                                feed_dict={X_input: X_batch, y_input: y_batch, keep_prob_v: 1.0,
                                                  batch_size_v: test_samples_num})
        val_acc = _acc
        val_loss = _cost
        out_str = "epoch {}, train loss={:.6f}, acc={:.6f}; test loss={:.6f}, acc={:.6f}; time cost: {:.2f} seconds".\
              format(epoch + 1, train_loss, train_acc, val_loss,val_acc, time.time() - t_epoch)
        print(out_str)
        f_obj.writelines(out_str+'\n')
        f_obj.flush()

        history['acc'].append(train_acc)
        history['val_acc'].append(val_acc)
        history['loss'].append(train_loss)
        history['val_loss'].append(val_loss)

        # if epoch%10==0 and epoch !=0:
        saver.save(session,'train_log/hyperRNN',global_step=(epoch+1)*batch_num)

    f_obj.close()

    # list all data in history
    print(history.keys())

    # summarize history for accuracy
    plt.figure(0)
    plt.plot(history['acc'])
    plt.plot(history['val_acc'])
    plt.title('model accuracy')
    plt.ylabel('accuracy')
    plt.xlabel('epoch')
    plt.legend(['train', 'test'], loc='upper left')
    # plt.show()
    plt.savefig('%s_acc_his_%d.png'%(datetime_str,random.randint(1,1000)),dpi=300)
    # summarize history for loss
    plt.figure(1)
    plt.plot(history['loss'])
    plt.plot(history['val_loss'])
    plt.title('model loss')
    plt.ylabel('loss')
    plt.xlabel('epoch')
    plt.legend(['train', 'test'], loc='upper left')
    # plt.show()
    plt.savefig('%s_loss_his_%d.png'%(datetime_str,random.randint(1,1000)),dpi=300)


    t1 = time.time()
    total = t1 - t0
    print('complete, total time cost: %.2f seconds or %.2f minutes or %.2f hours' % (total,total/60.0,total/3600.0))





if __name__ == "__main__":
    usage = "usage: %prog [options] label_image multi_spectral_images"
    parser = OptionParser(usage=usage, version="1.0 2018-4-10")
    parser.description = 'Introduction: classification multi-spectral remote sensing images using RNN '

    (options, args) = parser.parse_args()
    if len(sys.argv) < 2 or len(args) < 1:
        parser.print_help()
        sys.exit(2)

    # if options.para_file is None:
    #     basic.outputlogMessage('error, parameter file is required')
    #     sys.exit(2)

    # main(options, args)

    # inference('HSI/2018_IEEE_GRSS_DFC_HSI_TR', 'train_log','class_output.tif')
    # inference('HSI/2018_IEEE_GRSS_DFC_HSI_TR_0.5m.tif', 'train_log', 'class_output_0.5m_dropout_1.0.tif')

    inference('/DATA3/hlc/Data/2018_IEEE_GRSS_Data_Fusion/2018IEEE_Contest/Phase2/FullHSIDataset/20170218_UH_CASI_S4_NAD83_0.5m.tif',
              'train_log', 'class_output_all_area_0.5m.tif')

