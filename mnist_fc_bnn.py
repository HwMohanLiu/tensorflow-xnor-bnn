from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import sys
import os.path
import argparse

from tensorflow.examples.tutorials.mnist import input_data
from tensorflow.python import debug as tf_debug

import tensorflow as tf
from binary_net import BinaryNet

BN_TRAIN_PHASE = 1
BN_TEST_PHASE = 0

def create_dir_if_not_exists(dir):
    if not os.path.exists(dir):
        dir += '/1'
    else:
        sub_dir = str(int(next(os.walk(dir))[1][-1]) + 1)
        dir += '/' + sub_dir
    os.makedirs(dir)
    print('Logging to %s' % dir)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    '''
    parser.add_argument(
        'sub', help='sub-directory under --train_dir for logging events and checkpointing.   \
        Would usually give a unique name (e.g initial learning rate used) so that tensorboard \
        results are more easily interpreted')
    '''
    parser.add_argument('--data_dir', type=str, default='/scratch/gallowaa/mnist',
                        help='directory for storing input data')
    parser.add_argument('--train_dir', type=str, default='/scratch/gallowaa/logs/tf-bnn',
                        help='root path for logging events and checkpointing')
    parser.add_argument(
        '--n_hidden', help='number of hidden units', type=int, default=512)
    parser.add_argument(
        '--batch_size', help='examples per mini-batch', type=int, default=100)
    parser.add_argument(
        '--max_steps', help='maximum training steps', type=int, default=1000)
    parser.add_argument(
        '--binary', help="should weights and activations be constrained to -1, +1", action="store_true")
    parser.add_argument(
        '--fast', help="if binary flag is passed, determines if xnor_gemm cuda kernel is used to accelerate training, otherwise no effect", action="store_true")
    parser.add_argument(
        '--batch_norm', help="batch normalize activations", action="store_true")
    parser.add_argument(
        '--debug', help="run with tfdbg", action="store_true")
    args = parser.parse_args()

    # handle command line args
    if args.binary:
        print("Using 1-bit weights and activations")
        binary = True
        sub_1 = '/bin/'
        if args.fast:
            print("Using fast xnor_gemm kernel")
            fast = True
            sub_2 = 'xnor/'
        else:
            sub_2 = 'matmul/'
            fast = False
    else:
        sub_1 = '/fp/'
        sub_2 = ''
        binary = False
        fast = False

    log_path = args.train_dir + sub_1 + sub_2 + 'hid_' + str(args.n_hidden) + '/'
    if args.batch_norm:
        print("Using batch normalization")
        batch_norm = True
        alpha = 0.1
        epsilon = 1e-4
        log_path += 'batch_norm/'
    else:
        batch_norm = False

    log_path += 'bs_' + str(args.batch_size)

    #log_path = os.path.join(log_path, args.sub)
    create_dir_if_not_exists(log_path)
    '''
    # import data
    if binary:
        mnist = input_data.read_data_sets(
            args.data_dir, dtype=tf.uint8, one_hot=True)
        x = tf.placeholder(tf.int32, [None, 784])
    else:
        mnist = input_data.read_data_sets(
            args.data_dir, dtype=tf.float32, one_hot=True)
        x = tf.placeholder(tf.float32, [None, 784])

    phase = tf.placeholder(tf.bool, name='phase')

    # create the model
    bnn = BinaryNet(binary, fast, args.n_hidden, x, batch_norm, phase)
    y = bnn.output
    y_ = tf.placeholder(tf.float32, [None, 10])

    # define loss and optimizer
    cross_entropy = tf.reduce_mean(
        tf.nn.softmax_cross_entropy_with_logits(labels=y_, logits=y))

    # for batch-normalization
    if batch_norm:
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        with tf.control_dependencies(update_ops):
            # ensures that we execute the update_ops before performing the
            # train_op
            train_op = tf.train.AdamOptimizer(0.01).minimize(cross_entropy)
    else:
        train_op = tf.train.AdamOptimizer(0.01).minimize(cross_entropy)

    correct_prediction = tf.equal(tf.argmax(y, 1), tf.argmax(y_, 1))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

    #sess = tf.InteractiveSession()
    # tf.global_variables_initializer().run()
    sess = tf.Session()
    sess.run(tf.global_variables_initializer())

    if args.debug:
        print("Using debug mode")
        sess = tf_debug.LocalCLIDebugWrapperSession(sess)
        sess.add_tensor_filter("has_inf_or_nan", tf_debug.has_inf_or_nan)

    # setup summary writer
    summary_writer = tf.summary.FileWriter(log_path, sess.graph)
    training_summary = tf.summary.scalar("train loss", cross_entropy)
    test_summary = tf.summary.scalar("test acc.", accuracy)
    layer_1_summ = bnn.layer_1_summ

    # Train
    for step in range(args.max_steps):

        batch_xs, batch_ys = mnist.train.next_batch(args.batch_size)

        if binary:
            __, loss, train_summ = sess.run([train_op, cross_entropy, training_summary],
                                            feed_dict={x: batch_xs.astype('int32'), y_: batch_ys.astype('int32')})
        else:
            if batch_norm:
                __, loss, train_summ, l1_summ = sess.run([train_op, cross_entropy, training_summary, layer_1_summ],
                                                         feed_dict={x: batch_xs, y_: batch_ys, phase: BN_TRAIN_PHASE})
            else:
                __, loss, train_summ, l1_summ = sess.run([train_op, cross_entropy, training_summary, layer_1_summ],
                                                         feed_dict={x: batch_xs, y_: batch_ys})

        if step % 100 == 0:
            # Test trained model
            if binary:
                test_batch_xs, test_batch_ys = mnist.test.next_batch(
                    args.batch_size)
                test_acc, test_summ = sess.run([accuracy, test_summary], feed_dict={
                    x: test_batch_xs.astype('int32'), y_: test_batch_ys.astype('int32')})
            else:
                if batch_norm:
                    test_acc, test_summ = sess.run([accuracy, test_summary], feed_dict={x: mnist.test.images,
                                                                                        y_: mnist.test.labels, phase: BN_TEST_PHASE})
                else:
                    test_acc, test_summ = sess.run([accuracy, test_summary], feed_dict={x: mnist.test.images,
                                                                                        y_: mnist.test.labels})
            print("step %d, loss = %.4f, test accuracy %.4f" %
                  (step, loss, test_acc))

            summary_writer.add_summary(l1_summ, step)
            summary_writer.add_summary(train_summ, step)
            summary_writer.add_summary(test_summ, step)
            summary_writer.flush()

    # Test trained model
    if binary:
        print("Final test accuracy %.4f" % (sess.run(accuracy, feed_dict={x: mnist.test.images.astype('int32'),
                                                                          y_: mnist.test.labels.astype('int32')})))
    else:
        if batch_norm:
            print("Final test accuracy %.4f" % (sess.run(accuracy, feed_dict={x: mnist.test.images,
                                                                              y_: mnist.test.labels,
                                                                              phase: BN_TEST_PHASE})))
        else:
            print("Final test accuracy %.4f" % (sess.run(accuracy, feed_dict={x: mnist.test.images,
                                                                              y_: mnist.test.labels})))
    '''                                                                              