/** Display labels only; requests always retain the exact Ollama tag. */
export function modelLabel(tag:string):string {
 const known:Record<string,string>={
  'qwen3.5:397b-cloud':'Qwen 3.5', 'nemotron-3-super:cloud':'Nemotron 3 Super',
  'deepseek-v4-flash:cloud':'DeepSeek V4 Flash', 'glm-5.2:cloud':'GLM 5.2',
  'kimi-k3:cloud':'Kimi K3', 'kimi-k2.6:cloud':'Kimi K2.6',
  'minimax-m2.7:cloud':'MiniMax M2.7', 'llama3.2:latest':'Llama 3.2 3B',
  'llama3.2:3b':'Llama 3.2 3B', 'nomic-embed-text:latest':'Nomic Embed',
  'gpt-oss:120b-cloud':'GPT OSS 120B', 'gemma4:31b-cloud':'Gemma 4 31B',
  'qwen2.5-coder:3b':'Qwen Coder 3B', 'qwen3-vl:4b':'Qwen3 VL 4B',
 };
 return known[tag] ?? tag.replace(/:latest$/, '').replace(/[-:]cloud$/, '');
}
