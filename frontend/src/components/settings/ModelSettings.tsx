import { useState } from "react";
import { CheckCircle2, KeyRound, Loader2, Save, Trash2, Wifi } from "lucide-react";

export type ModelSettingsValue = {
  api_key: string;
  base_url: string;
  model: string;
};

type Props = {
  value: ModelSettingsValue;
  onChange: (value: ModelSettingsValue) => void;
  onSave: () => void;
  onClear: () => void;
  onTest: () => Promise<void>;
  testing: boolean;
  status: string;
};

export default function ModelSettings({ value, onChange, onSave, onClear, onTest, testing, status }: Props) {
  const [showKey, setShowKey] = useState(false);
  const update = (key: keyof ModelSettingsValue, next: string) => onChange({ ...value, [key]: next });
  return <section className="model-settings">
    <div className="model-settings-heading"><div><KeyRound size={17} /><strong>模型 API 配置</strong></div><span>仅保存在当前页面内存中</span></div>
    <label>API Key
      <input type={showKey ? "text" : "password"} autoComplete="off" value={value.api_key} onChange={event => update("api_key", event.target.value)} placeholder="输入你的模型 API Key" />
    </label>
    <button type="button" className="text-action" onClick={() => setShowKey(current => !current)}>{showKey ? "隐藏 Key" : "显示 Key"}</button>
    <label>Base URL
      <input value={value.base_url} onChange={event => update("base_url", event.target.value)} placeholder="https://api.openai.com/v1" />
    </label>
    <label>模型名称
      <input value={value.model} onChange={event => update("model", event.target.value)} placeholder="gpt-4o-mini" />
    </label>
    <p className="model-settings-note">Key 仅随请求发送至后端，不写入数据库或浏览器持久存储。刷新页面后需要重新输入。仅支持 HTTPS 公网地址。</p>
    <div className="model-settings-actions">
      <button type="button" onClick={onTest} disabled={testing || !value.api_key.trim()}>{testing ? <Loader2 className="spin" size={14} /> : <Wifi size={14} />} 测试连接</button>
      <button type="button" onClick={onSave}><Save size={14} /> 保存到本次页面</button>
      <button type="button" className="secondary" onClick={onClear}><Trash2 size={14} /> 清除</button>
    </div>
    {status && <p className="model-settings-status"><CheckCircle2 size={14} />{status}</p>}
  </section>;
}
