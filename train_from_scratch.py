import tensorflow as tf
from yolo.yolo_v3 import YOLOV3
from configuration import CATEGORY_NUM, IMAGE_HEIGHT, IMAGE_WIDTH, CHANNELS, EPOCHS, BATCH_SIZE, \
    save_model_dir, save_frequency, test_picture_dir, save_test_results_dir, save_test_results_or_not, \
    load_weights_before_training, load_weights_from_epoch
from yolo.loss import YoloLoss
from data_process.make_dataset import generate_dataset
from yolo.make_label import GenerateLabel
from test_on_single_image import single_image_inference
import cv2
import os
from utils.preprocess import process_image_filenames


def print_model_summary(network):
    network.build(input_shape=(None, IMAGE_HEIGHT, IMAGE_WIDTH, CHANNELS))
    network.summary()


def generate_label_batch(true_boxes):
    true_label = GenerateLabel(true_boxes=true_boxes.numpy(), input_shape=[IMAGE_HEIGHT, IMAGE_WIDTH]).generate_label()
    return true_label


if __name__ == '__main__':
    # GPU settings
    gpus = tf.config.experimental.list_physical_devices('GPU')
    if gpus:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)

    # dataset
    train_dataset, train_count = generate_dataset()

    net = YOLOV3(out_channels=3 * (CATEGORY_NUM + 5))
    print_model_summary(network=net)

    if load_weights_before_training:
        net.load_weights(filepath=save_model_dir+"epoch-{}".format(load_weights_from_epoch))
        print("Successfully load weights!")
    else:
        load_weights_from_epoch = -1

    # loss and optimizer
    yolo_loss = YoloLoss()
    lr_schedule = tf.keras.optimizers.schedules.ExponentialDecay(
        initial_learning_rate=0.001,
        decay_steps=3000,
        decay_rate=0.96,
        staircase=True
    )
    optimizer = tf.optimizers.RMSprop(learning_rate=lr_schedule)


    # metrics
    loss_metric = tf.metrics.Mean()

    def train_step(image_batch, label_batch):
        with tf.GradientTape() as tape:
            yolo_output = net(image_batch, training=True)
            loss = yolo_loss(y_true=label_batch, y_pred=yolo_output)
        gradients = tape.gradient(loss, net.trainable_variables)
        optimizer.apply_gradients(grads_and_vars=zip(gradients, net.trainable_variables))
        loss_metric.update_state(values=loss)


    for epoch in range(load_weights_from_epoch + 1, EPOCHS):
        step = 0
        for images, boxes in train_dataset:
            step += 1
            labels = generate_label_batch(true_boxes=boxes)
            train_step(image_batch=process_image_filenames(images), label_batch=labels)
            print("Epoch: {}/{}, step: {}/{}, loss: {:.5f}".format(epoch,
                                                                   EPOCHS,
                                                                   step,
                                                                   tf.math.ceil(train_count / BATCH_SIZE),
                                                                   loss_metric.result()))

        loss_metric.reset_states()

        # save test result on single test image
        if save_test_results_or_not:
            test_image = single_image_inference(image_dir=test_picture_dir, model=net)
            cv2.imwrite(filename=os.path.join(save_test_results_dir, "epoch-{}-result.jpg".format(epoch)), img=test_image)

        if epoch % save_frequency == 0:
            net.save_weights(filepath=save_model_dir+"epoch-{}".format(epoch), save_format='tf')

    net.save_weights(filepath=save_model_dir+"saved_model", save_format='tf')