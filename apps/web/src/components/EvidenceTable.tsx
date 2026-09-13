import type { EvidenceFragment } from "../api";

/** 证据片段表（实体页弹层与证据工作台共用的展示组件）。 */
export function EvidenceTable({ fragments }: { fragments: EvidenceFragment[] }) {
  if (fragments.length === 0) return <div className="state-empty">该声明没有登记证据片段。</div>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>来源文档</th>
          <th>字段路径</th>
          <th>原始值</th>
          <th>内容哈希</th>
          <th>链接</th>
        </tr>
      </thead>
      <tbody>
        {fragments.map((f) => (
          <tr key={f.fragment_id}>
            <td>{f.document_title}</td>
            <td>
              <code>{f.field_path}</code>
            </td>
            <td>{f.raw_value}</td>
            <td>
              <code title={f.content_sha256}>{f.content_sha256.slice(0, 12)}…</code>
            </td>
            <td>
              {f.source_url ? (
                <a href={f.source_url} target="_blank" rel="noreferrer">
                  来源
                </a>
              ) : (
                "—"
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
