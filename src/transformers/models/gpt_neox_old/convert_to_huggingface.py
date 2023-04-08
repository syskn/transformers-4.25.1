# coding=utf-8
# Copyright 2021 The rinna Team All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import yaml
import os
import argparse

import torch

from modeling_gpt_neox import GPTNeoXForCausalLM
from configuration_gpt_neox import GPTNeoXConfig


def get_state_dict_from_checkpoint_dir(checkpoint_dir, num_layers):
    tgt_state_dict = {}

    # word embedding
    src_state_dict = torch.load(os.path.join(checkpoint_dir, "layer_00-model_00-model_states.pt"))
    tgt_state_dict["transformer.wte.weight"] = src_state_dict["word_embeddings.weight"]

    # layers
    for layer_idx in range(1, num_layers+1):
        src_state_dict = torch.load(os.path.join(checkpoint_dir, f"layer_{layer_idx+1:02}-model_00-model_states.pt"))
        
        # ln_1
        tgt_state_dict[f"transformer.h.{layer_idx-1}.ln_1.weight"] = src_state_dict["input_layernorm.weight"]
        tgt_state_dict[f"transformer.h.{layer_idx-1}.ln_1.bias"] = src_state_dict["input_layernorm.bias"]
        
        # attn.bias, attn.masked_bias: ignored

        # qkv_proj
        tgt_state_dict[f"transformer.h.{layer_idx-1}.attn.qkv_proj.weight"] = src_state_dict["attention.query_key_value.weight"]
        tgt_state_dict[f"transformer.h.{layer_idx-1}.attn.qkv_proj.bias"] = src_state_dict["attention.query_key_value.bias"]

        # out_proj
        tgt_state_dict[f"transformer.h.{layer_idx-1}.attn.out_proj.weight"] = src_state_dict["attention.dense.weight"]
        tgt_state_dict[f"transformer.h.{layer_idx-1}.attn.out_proj.bias"] = src_state_dict["attention.dense.bias"]

        # ln_2
        tgt_state_dict[f"transformer.h.{layer_idx-1}.ln_2.weight"] = src_state_dict["post_attention_layernorm.weight"]
        tgt_state_dict[f"transformer.h.{layer_idx-1}.ln_2.bias"] = src_state_dict["post_attention_layernorm.bias"]

        # mlp
        tgt_state_dict[f"transformer.h.{layer_idx-1}.mlp.fc_in.weight"] = src_state_dict["mlp.dense_h_to_4h.weight"]
        tgt_state_dict[f"transformer.h.{layer_idx-1}.mlp.fc_in.bias"] = src_state_dict["mlp.dense_h_to_4h.bias"]
        tgt_state_dict[f"transformer.h.{layer_idx-1}.mlp.fc_out.weight"] = src_state_dict["mlp.dense_4h_to_h.weight"]
        tgt_state_dict[f"transformer.h.{layer_idx-1}.mlp.fc_out.bias"] = src_state_dict["mlp.dense_4h_to_h.bias"]

    # final norm
    src_state_dict = torch.load(os.path.join(checkpoint_dir, f"layer_{num_layers+3:02}-model_00-model_states.pt"))
    tgt_state_dict["transformer.ln_f.weight"] = src_state_dict["norm.weight"]
    tgt_state_dict["transformer.ln_f.bias"] = src_state_dict["norm.bias"]

    # output layer
    src_state_dict = torch.load(os.path.join(checkpoint_dir, f"layer_{num_layers+4:02}-model_00-model_states.pt"))
    tgt_state_dict["lm_head.weight"] = src_state_dict["final_linear.weight"]

    return tgt_state_dict


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint_dir", type=str, required=True, help="directory that contains state dict pt files and a config directory generated by gpt-neox")
    parser.add_argument("--hf_config_path", type=str, required=True, help="path to Huggingface GPT-NeoX configuration file")
    parser.add_argument("--hf_save_dir", type=str, required=True, help="directory to save Huggingface GPT-NeoX model weights and configuration")
    args = parser.parse_args()

    config_dir = os.path.join(args.checkpoint_dir, "configs")
    config_filenames = list(filter(
        lambda x: x.endswith("yml"),
        os.listdir(config_dir)
    ))
    config = {}
    for filename in config_filenames:
        with open(os.path.join(config_dir, filename)) as f:
            data = f.read()
        yaml_dict = yaml.load(data, Loader=yaml.CLoader)
        config.update(yaml_dict)
    
    state_dict = get_state_dict_from_checkpoint_dir(args.checkpoint_dir, config["num-layers"])

    config = GPTNeoXConfig.from_json_file(args.hf_config_path)
    model = GPTNeoXForCausalLM(config)

    missing_keys, unexpected_keys = model.load_state_dict(state_dict, strict=False)
    print(f"missing keys: {missing_keys}")
    print(f"unexpected keys: {unexpected_keys}")

    model.save_pretrained(args.hf_save_dir)