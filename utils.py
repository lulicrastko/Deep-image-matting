import os
import random

import cv2 as cv
import keras.backend as K
import numpy as np
from keras.utils.training_utils import multi_gpu_model
from tensorflow.python.client import device_lib

kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (3, 3))
with open('Combined_Dataset/Training_set/training_fg_names.txt') as f:
    fg_files = f.read().splitlines()


# simple alpha prediction loss
def custom_loss(y_true, y_pred):
    epsilon = 1e-6
    epsilon_sqr = K.constant(epsilon ** 2)
    return K.mean(K.sqrt(K.square(y_pred - y_true) + epsilon_sqr))


# getting the number of GPUs
def get_available_gpus():
    local_device_protos = device_lib.list_local_devices()
    return [x.name for x in local_device_protos if x.device_type == 'GPU']


def do_compile(model):
    num_gpu = len(get_available_gpus())
    if num_gpu >= 2:
        model = multi_gpu_model(model, gpus=num_gpu)

    # sgd = SGD(lr=1e-3, decay=1e-6, momentum=0.99, nesterov=True)
    model.compile(optimizer='nadam', loss=custom_loss)
    return model


def get_alpha(name):
    fg_i = int(name.split("_")[0])
    name = fg_files[fg_i]
    filename = os.path.join('mask', name)
    alpha = cv.imread(filename, 0)
    return alpha


def generate_trimap(alpha):
    iter = random.randint(1, 20)
    fg = alpha.copy()
    fg[alpha != 255] = 0
    unknown = alpha.copy()
    unknown[alpha != 0] = 255
    unknown = cv.dilate(unknown, kernel, iterations=iter)
    trimap = np.sign(unknown - fg) * 128 + fg
    return np.array(trimap).astype(np.uint8)


def get_crop_top_left(trimap):
    h, w = trimap.shape[:2]
    x, y = 0, 0
    for i in range(10):
        if w > 320:
            x = random.randint(0, w - 320)
        if h > 320:
            y = random.randint(0, h - 320)
        if trimap[y + 160, x + 160] == 128:
            break
    return x, y


def ensure_size(matrix, channel):
    h, w = matrix.shape[:2]
    if h >= 320 and w >= 320:
        return matrix

    if channel > 1:
        ret = np.zeros((320, 320, channel), dtype=np.float32)
        ret[0:h, 0:w, :] = matrix[:, :, :]
    else:
        ret = np.zeros((320, 320), dtype=np.float32)
        ret[0:h, 0:w] = matrix[:, :]
    return ret


def data_gen(usage):
    filename = '{}_names.txt'.format(usage)
    with open(filename, 'r') as f:
        names = f.read().splitlines()
    batch_size = 16
    i = 0
    while True:
        batch_x = np.empty((batch_size, 320, 320, 4), dtype=np.float32)
        batch_y = np.empty((batch_size, 320, 320, 1), dtype=np.float32)

        for i_batch in range(batch_size):
            name = names[i]
            filename = os.path.join('merged', name)
            bgr_img = cv.imread(filename)
            bg_h, bg_w = bgr_img.shape[:2]
            a = get_alpha(name)
            a_h, a_w = a.shape[:2]
            alpha = np.zeros((bg_h, bg_w), np.float32)
            alpha[0:a_h, 0:a_w] = a
            trimap = generate_trimap(alpha)
            x, y = get_crop_top_left(trimap)
            bgr_img = bgr_img[y:y + 320, x:x + 320]
            bgr_img = ensure_size(bgr_img, 3)
            trimap = trimap[y:y + 320, x:x + 320]
            trimap = ensure_size(trimap, 1)
            alpha = alpha[y:y + 320, x:x + 320]
            alpha = ensure_size(alpha, 1)
            batch_x[i_batch, :, :, 0:3] = bgr_img / 255.
            batch_x[i_batch, :, :, 3] = trimap / 255.
            batch_y[i_batch, :, :, 0] = alpha / 255.

            i += 1
            if i >= len(names):
                i = 0

        yield batch_x, batch_y


def train_gen():
    return data_gen('train')


def valid_gen():
    return data_gen('valid')


if __name__ == '__main__':
    filename = 'merged/357_35748.png'
    bgr_img = cv.imread(filename)
    bg_h, bg_w = bgr_img.shape[:2]
    print(bg_w, bg_h)
