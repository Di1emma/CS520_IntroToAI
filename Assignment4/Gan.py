from __future__ import print_function, division
from convert import reshape
from keras.layers import Input, Concatenate
from keras.layers import BatchNormalization
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import UpSampling2D, Conv2D
from keras.models import Model
import matplotlib.pyplot as plt
from data_loader import DataLoader
import numpy as np
import os
import scipy.misc

import scipy

model_save_path = './saved_model/'

class Pix2Pix():
    def __init__(self):
        self.img_rows = 256
        self.img_cols = 256
        self.channels = 3
        self.img_shape = (self.img_rows, self.img_cols, self.channels)

        self.data_loader = DataLoader(img_res=(self.img_rows, self.img_cols))

        patch = int(self.img_rows / 2 ** 4)
        self.disc_patch = (patch, patch, 1)

        self.gf = 64
        self.df = 64

        self.discriminator = self.build_discriminator()
        self.discriminator.compile(loss='mse',
                                   loss_weights=[1],
                                   optimizer='sgd',
                                   metrics=['accuracy'])

        self.generator = self.build_generator()

        img_A = Input(shape=self.img_shape)
        img_B = Input(shape=self.img_shape)

        fake_A = self.generator(img_B)

        self.discriminator.trainable = False

        valid = self.discriminator([fake_A, img_B])

        self.combined = Model(inputs=[img_A, img_B], outputs=[valid, fake_A])
        self.combined.compile(loss=['mse', 'mae'],
                              loss_weights=[1, 100],
                              optimizer='sgd')

    def build_generator(self):

        def conv2d(layer_input, filters, f_size=4, bn=True):
            d = Conv2D(filters, kernel_size=f_size, strides=2, padding='same')(layer_input)
            d = LeakyReLU(alpha=0.2)(d)
            if bn:
                d = BatchNormalization(momentum=0.8)(d)
            return d

        def deconv2d(layer_input, skip_input, filters, f_size=4):
            u = UpSampling2D(size=2)(layer_input)
            u = Conv2D(filters, kernel_size=f_size, strides=1, padding='same', activation='relu')(u)
            u = BatchNormalization(momentum=0.8)(u)
            u = Concatenate()([u, skip_input])
            return u

        d0 = Input(shape=self.img_shape)

        d1 = conv2d(d0, self.gf, bn=False)
        d2 = conv2d(d1, self.gf * 2)
        d3 = conv2d(d2, self.gf * 4)
        d4 = conv2d(d3, self.gf * 8)
        d5 = conv2d(d4, self.gf * 8)
        d6 = conv2d(d5, self.gf * 8)
        d7 = conv2d(d6, self.gf * 8)

        u1 = deconv2d(d7, d6, self.gf * 8)
        u2 = deconv2d(u1, d5, self.gf * 8)
        u3 = deconv2d(u2, d4, self.gf * 8)
        u4 = deconv2d(u3, d3, self.gf * 4)
        u5 = deconv2d(u4, d2, self.gf * 2)
        u6 = deconv2d(u5, d1, self.gf)

        u7 = UpSampling2D(size=2)(u6)
        output_img = Conv2D(self.channels, kernel_size=4, strides=1, padding='same', activation='tanh')(u7)

        return Model(d0, output_img)

    def build_discriminator(self):

        def d_layer(layer_input, filters, f_size=4, bn=True):
            d = Conv2D(filters, kernel_size=f_size, strides=2, padding='same')(layer_input)
            d = LeakyReLU(alpha=0.2)(d)
            if bn:
                d = BatchNormalization(momentum=0.8)(d)
            return d

        img_A = Input(shape=self.img_shape)
        img_B = Input(shape=self.img_shape)

        combined_imgs = Concatenate(axis=-1)([img_A, img_B])

        d1 = d_layer(combined_imgs, self.df, bn=False)
        d2 = d_layer(d1, self.df * 2)
        d3 = d_layer(d2, self.df * 4)
        d4 = d_layer(d3, self.df * 8)

        validity = Conv2D(1, kernel_size=4, strides=1, padding='same')(d4)

        return Model([img_A, img_B], validity)

    def train(self, epochs,  batch_size, sample_interval):
        acc = 0
        valid = np.ones((batch_size,) + self.disc_patch)
        fake = np.zeros((batch_size,) + self.disc_patch)

        for epoch in range(epochs):
            for batch_i, (imgs_A, imgs_B) in enumerate(self.data_loader.load_train_batch(batch_size)):

                fake_A = self.generator.predict(imgs_B)
                d_loss_real = self.discriminator.train_on_batch([imgs_A, imgs_B], valid)
                d_loss_fake = self.discriminator.train_on_batch([fake_A, fake])
                d_loss = 0.5 * np.add(d_loss_real, d_loss_fake)
                g_loss = self.combined.train_on_batch([imgs_A, imgs_B], [valid,imgs_A])
                print("[Epoch %d/%d] [Batch %d/%d] [D loss: %f, D_acc: %3d%%] [G loss: %f]" % (
                epoch + 1, epochs, batch_i + 1, self.data_loader.n_batches, d_loss[0], 100 * d_loss[1],g_loss[0]))

                if batch_i == sample_interval-1:
                    acc = self.sample_images(epoch, acc, batch_size)
                    #self.generator.save_weights(model_save_path + 'generator_weights.h5')

    def sample_images(self, epoch, acc, batch_size):
        for batch_i, (imgs_A, imgs_B) in enumerate(self.data_loader.load_test_batch(batch_size)):
            os.makedirs('test_result/contrast/%d' % epoch, exist_ok=True)
            fake_A = self.generator.predict(imgs_B)
            gen_imgs = np.concatenate([imgs_B, fake_A, imgs_A])
            gen_imgs = 0.5 * gen_imgs + 0.5
            titles = ['BW', 'Fake', 'Origin']
            r, c = 3, 1
            fig, axs = plt.subplots(r, c)
            cnt = 0
            for i in range(r):
                axs[i].imshow(gen_imgs[cnt])
                axs[i].set_title(titles[i])
                axs[i].axis('off')
                cnt += 1
            fig.savefig("test_result/contrast/%d/%d.png" % (epoch, batch_i))
            os.makedirs('test_result/fake/%d' % epoch, exist_ok=True)
            scipy.misc.imsave("test_result/fake/%d/%d.jpg" % (epoch, batch_i), gen_imgs[1])
        plt.close()
        return acc


    def self_test(self):
        path = './self_test/'
        save_path = './self_result/'
        reshape(path, path)
        for batch_i, imgs_A in enumerate(self.data_loader.load_self_test_batch(1)):
            self.generator.load_weights(model_save_path + 'generator_weights.h5')
            fake_A = self.generator.predict(imgs_A)
            gen_imgs = np.concatenate([fake_A])
            gen_imgs = 0.5 * gen_imgs + 0.5
            scipy.misc.imsave(save_path + '/%d.jpg' % batch_i, gen_imgs[0])

if __name__ == '__main__':
    choice = input('Input test to test the model by youself, or input check to directly find some test result')
    if choice =='test':
        choice2 = input('Has already put the grayscale image with JPG format in self_test folder? (Y/N)')
        if choice2 == 'Y':
            print("You'd better make sure the test image should be 256*256 to get best colorization result!")
            print('Start test.')
            self_test = Pix2Pix()
            self_test.self_test()
            print('Fininsh test and you will get the test result in the self_result folder.')
        if choice2  =='N':
            print('Put the grayscale image with JPG format in self_result folder, then try test again.')
            print('There are many test image we provided in ./dataset_preprocessing/original folder and you can use them or find your own text images.')
    if choice == 'check':
        print('Find the test result in ./test_result/Final_test_result folder.')