from transformers import BertTokenizer, BertModel
import torch
from torch import nn

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

import numpy as np
from tqdm.auto import tqdm
import wandb

from dataloader import get_dataset
from utils import *


class EssayToAllBERT(nn.Module):
    """
    Comprises of a bert based self which takes tokenized essay and outputs:
    empathy, distress, 
    personality_conscientiousness, personality_openess, personality_extraversion,personality_agreeableness,personality_stability,
    iri_perspective_taking,iri_personal_distress,iri_fantasy,iri_empathatic_concern
    
    Total 11 Linear layers after transformers.BertModel instance
    
    """

    def __init__(self, cfg):
        self.cfg = cfg
        super().__init__()
        self.tokenizer = BertTokenizer.from_pretrained("bert-base-uncased",
                                                       do_lower_case=True)

        self.bert = BertModel.from_pretrained("bert-base-uncased")
        self.emotion_lin = nn.Linear(self.bert.config.hidden_size,
                                     self.cfg.num_classes)
        self.emotion_softmax = torch.nn.Softmax(dim=-1)

        self.empathy = nn.Linear(self.bert.config.hidden_size, 1)
        self.distress = nn.Linear(self.bert.config.hidden_size, 1)

        self.personality_conscientiousness = nn.Linear(
            self.bert.config.hidden_size, 1)
        self.personality_openess = nn.Linear(self.bert.config.hidden_size, 1)
        self.personality_extraversion = nn.Linear(self.bert.config.hidden_size,
                                                  1)
        self.personality_agreeableness = nn.Linear(self.bert.config.hidden_size,
                                                   1)
        self.personality_stability = nn.Linear(self.bert.config.hidden_size, 1)

        self.iri_perspective_taking = nn.Linear(self.bert.config.hidden_size, 1)
        self.iri_fantasy = nn.Linear(self.bert.config.hidden_size, 1)
        self.iri_personal_distress = nn.Linear(self.bert.config.hidden_size, 1)
        self.iri_empathatic_concern = nn.Linear(self.bert.config.hidden_size, 1)

        self.device = torch.device(
            "cuda") if torch.cuda.is_available() else torch.device("cpu")

        self.load_all_to_device(self.device)

    def load_all_to_device(self, device):
        self.bert = self.bert.to(device)

        self.emotion_lin = self.emotion_lin.to(device)
        self.emotion_softmax = self.emotion_softmax.to(device)

        self.empathy = self.empathy.to(device)
        self.distress = self.distress.to(device)

        self.personality_conscientiousne = self.personality_conscientiousness.to(
            device)
        self.personality_openess = self.personality_openess.to(device)
        self.personality_extraversion = self.personality_extraversion.to(device)
        self.personality_agreeableness = self.personality_agreeableness.to(
            device)
        self.personality_stability = self.personality_stability.to(device)
        self.iri_perspective_taking = self.iri_perspective_taking.to(device)
        self.iri_fantasy = self.iri_fantasy.to(device)
        self.iri_personal_distress = self.iri_personal_distress.to(device)
        self.iri_empathatic_concern = self.iri_empathatic_concern.to(device)

    def forward(self, batch):

        x = self.bert(**batch[0])[1]  # (batch_size, hidden_size)

        emotion = self.emotion_lin(x)
        emotion = self.emotion_softmax(emotion)

        empathy = self.empathy(x)
        distress = self.distress(x)

        personality_conscientiousness = self.personality_conscientiousness(x)
        personality_openess = self.personality_openess(x)
        personality_extraversion = self.personality_extraversion(x)
        personality_agreeableness = self.personality_agreeableness(x)
        personality_stability = self.personality_stability(x)
        iri_perspective_taking = self.iri_perspective_taking(x)
        iri_fantasy = self.iri_fantasy(x)
        iri_personal_distress = self.iri_personal_distress(x)
        iri_empathatic_concern = self.iri_empathatic_concern(x)

        return (emotion, empathy, distress, personality_conscientiousness,
                personality_openess, personality_extraversion,
                personality_agreeableness, personality_stability,
                iri_perspective_taking, iri_fantasy, iri_personal_distress,
                iri_empathatic_concern)

    def get_criteria(self):
        criteria = []
        if self.cfg.classification_loss == "categorical_crossentropy":
            criteria += [nn.CrossEntropyLoss()]
        if self.cfg.regression_loss == "mean_squared_error":
            criteria += [nn.MSELoss()] * 11
        return criteria

    def fit(self):
        device = torch.device(
            "cuda") if torch.cuda.is_available() else torch.device("cpu")

        optimizer = get_optimizer(self.cfg, self.parameters())
        criteria = self.get_criteria()

        train_ds, val_ds = get_dataset(self.cfg)

        for epoch in range(self.cfg.epochs):
            progress_bar = tqdm(range(len(train_ds)))
            self.train()
            epoch_loss = []
            epoch_acc = []
            epoch_f1 = []
            progress_bar.set_description(f"Epoch {epoch}")
            for batchnum, batch in enumerate(train_ds):
                batch["inputs"][0] = self.tokenizer(text=batch["inputs"][0],
                                                    add_special_tokens=True,
                                                    return_attention_mask=True,
                                                    max_length=self.cfg.maxlen,
                                                    padding='max_length',
                                                    truncation=True,
                                                    return_tensors="pt")

                batch = self.push_batch_to_device(batch)

                outputs = self(batch)

                loss = criteria[0](outputs[0], batch["outputs"][0])
                # for i in range(len(outputs)):
                #     loss += criteria[i](outputs[i],batch[i+1])

                loss.backward()

                # loss
                optimizer.step()
                optimizer.zero_grad()
                np_batch_outputs = batch["outputs"][0].detach().cpu().numpy()
                np_outputs = outputs[0].detach().cpu().numpy()

                acc = accuracy(np_batch_outputs, np_outputs)
                f1 = f1_loss(np_batch_outputs, np_outputs)
                loss_ = loss.detach().cpu().numpy()

                epoch_loss.append(loss_)
                epoch_acc.append(acc)
                epoch_f1.append(f1)
                progress_bar.set_postfix(loss=loss_, accuracy=acc, f1=f1)
                progress_bar.update(1)

            progress_bar.set_postfix(loss=np.mean(epoch_loss),
                                     accuracy=np.mean(epoch_acc),
                                     f1=np.mean(epoch_f1))

            state = {
                'epoch': epoch,
                'state_dict': self.state_dict(),
                'optimizer': optimizer.state_dict(),
            }
            torch.save(state, f"./ckpts/bert_{epoch}.pt")

            # validation loop
            val_epoch_loss = []
            val_epoch_acc = []
            val_epoch_f1 = []
            self.eval()
            with torch.no_grad():
                for val_batch in val_ds:
                    val_batch["inputs"][0] = self.tokenizer(
                        text=val_batch["inputs"][0],
                        add_special_tokens=True,
                        return_attention_mask=True,
                        max_length=self.cfg.maxlen,
                        padding='max_length',
                        truncation=True,
                        return_tensors="pt")

                    val_batch = self.push_batch_to_device(val_batch)

                    val_outputs = self(val_batch)
                    val_loss = criteria[0](val_outputs[0],
                                           val_batch["outputs"][0])
                    # for i in range(len(val_outputs)):

                    #     val_loss +=
                    np_val_batch_outputs = val_batch["outputs"][0].detach().cpu(
                    ).numpy()
                    np_val_outputs = val_outputs[0].detach().cpu().numpy()

                    val_f1 = f1_loss(np_val_batch_outputs, np_val_outputs)
                    val_acc = accuracy(np_val_batch_outputs, np_val_outputs)

                    val_epoch_loss.append(val_loss.detach().cpu().numpy())
                    val_epoch_acc.append(val_acc)
                    val_epoch_f1.append(val_f1)
            progress_bar.close()

            tqdm.write(
                f"Val loss: {np.mean(val_epoch_loss)} Val accuracy: {np.mean(val_epoch_acc)} Val f1: {np.mean(val_epoch_f1)}"
            )

            val_cm = confusion_matrix(np_val_batch_outputs, np_val_outputs)

            ax = sns.heatmap(val_cm,
                             annot=True,
                             xticklabels=self.class_names,
                             yticklabels=self.class_names,
                             fmt="d")
            ax.get_figure().savefig("confusion.jpg")
            wandb.log({"val_confusion_matrix": wandb.Image("confusion.jpg")},
                      commit=False)

            plt.show()

            wandb.log({
                "epoch": epoch,
                "train loss": np.mean(epoch_loss),
                "train accuracy": np.mean(epoch_acc),
                "train macro f1": np.mean(epoch_f1),
                "val loss": np.mean(val_epoch_loss),
                "val accuracy": np.mean(val_epoch_acc),
                "val macro f1": np.mean(val_epoch_f1)
            })
