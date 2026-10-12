"""Upload this folder's files to the root of a Gradio ZeroGPU Space."""
import spaces  # Initialize ZeroGPU before importing torch.
import json
import os
from datetime import datetime, timezone

import gradio as gr
import torch
from jsonschema import Draft202012Validator
from lmformatenforcer import JsonSchemaParser
from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = 'NCAIR1/N-ATLaS'
token = os.environ.get('HF_TOKEN')
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=token)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, token=token, torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=True, attn_implementation='sdpa',
).to('cuda').eval()


def model_info():
    return {'ready': True, 'model_id': MODEL_ID, 'contract_version': 1,
            'runtime': 'Transformers BF16',
            'revision': getattr(model.config, '_commit_hash', None)}


@spaces.GPU(duration=120)
def generate_response(messages_json, max_tokens, format_schema_json):
    stage = 'request validation'
    try:
        if len(messages_json) > 64000 or len(format_schema_json) > 32000:
            raise ValueError('Request too large')
        messages = json.loads(messages_json)
        if not isinstance(messages, list) or not 1 <= len(messages) <= 40:
            raise ValueError('Invalid messages')
        if any(not isinstance(m, dict) or m.get('role') not in
               ('system', 'user', 'assistant') or not isinstance(m.get('content'), str)
               for m in messages):
            raise ValueError('Invalid message')
        if int(max_tokens) != max_tokens or not 1 <= max_tokens <= 600:
            raise ValueError('Invalid token limit')
        schema = json.loads(format_schema_json) if format_schema_json.strip() else None
        kwargs = {}
        if schema is not None:
            stage = 'schema setup'
            Draft202012Validator.check_schema(schema)
            kwargs['prefix_allowed_tokens_fn'] = build_transformers_prefix_allowed_tokens_fn(
                tokenizer, JsonSchemaParser(schema))
        stage = 'prompt preparation'
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            date_string=datetime.now(timezone.utc).strftime('%d %b %Y'))
        inputs = tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
        if inputs['input_ids'].shape[1] + max_tokens > 4096:
            raise ValueError('Conversation too long')
        inputs = inputs.to('cuda')
        stops = [tokenizer.eos_token_id]
        eot = tokenizer.convert_tokens_to_ids('<|eot_id|>')
        if eot is not None and eot != tokenizer.unk_token_id:
            stops.append(eot)
        with torch.inference_mode():
            stage = 'model generation'
            output = model.generate(
                **inputs, max_new_tokens=int(max_tokens), do_sample=False,
                eos_token_id=list(set(stops)), pad_token_id=tokenizer.eos_token_id,
                use_cache=True, **kwargs)
        stage = 'response decoding'
        answer = tokenizer.decode(output[0, inputs['input_ids'].shape[1]:],
                                  skip_special_tokens=True).strip()
        if schema is not None:
            stage = 'response schema validation'
            Draft202012Validator(schema).validate(json.loads(answer))
        if not answer:
            raise ValueError('Empty response')
        return answer
    except Exception as exc:
        # Do not expose prompts, credentials or model internals through API errors.
        print(f'Generation failed at {stage}: {type(exc).__name__}', flush=True)
        raise gr.Error(f'Generation failed at {stage} ({type(exc).__name__}).') from None


with gr.Blocks() as demo:
    gr.Markdown('# Parrot N-ATLaS generation\nBackend API for the Hausa learning app.')
    messages_input = gr.Textbox(label='Messages JSON', value='[{"role":"user","content":"Sannu"}]')
    token_limit = gr.Number(label='Maximum new tokens', value=80, precision=0)
    schema_input = gr.Textbox(label='Response JSON schema (optional)', value='')
    result = gr.Textbox(label='Model response')
    gr.Button('Generate').click(generate_response,
        [messages_input, token_limit, schema_input], result,
        api_name='generate_response', concurrency_limit=1)
    info = gr.JSON(label='Model status')
    gr.Button('Check status').click(model_info, [], info, api_name='model_info', queue=False)

if __name__ == '__main__':
    demo.queue(max_size=8).launch()
