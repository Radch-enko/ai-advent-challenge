import { RequestLog } from '../../domain/models/chat'

type Props = {
  log: RequestLog
  tab: 'request' | 'response'
  onTab: (tab: 'request' | 'response') => void
  onClose: () => void
}

export function RequestLogs({ log, tab, onTab, onClose }: Props) {
  const content = tab === 'request' ? log.request : log.response
  return <aside className="logs-panel"><header><div><b>Request Logs</b><span>Детали последнего вызова</span></div><button onClick={onClose}>×</button></header>
    <div className="log-meta"><span>Provider <b>{log.provider}</b></span><span>Model <b>{log.model}</b></span><span className="success">Status <b>{log.status}</b></span><span>Duration <b>{log.duration}</b></span></div>
    <div className="log-tabs"><button className={tab === 'request' ? 'active' : ''} onClick={() => onTab('request')}>Request</button><button className={tab === 'response' ? 'active' : ''} onClick={() => onTab('response')}>Response</button></div>
    <pre>{JSON.stringify(content, null, 2)}</pre>
  </aside>
}
