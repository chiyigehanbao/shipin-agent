import React from 'react'
import { Tag } from 'antd'
import './identity-reference.css'

const RISK_META = {
  stable: { color: 'success', label: '身份稳定' },
  review: { color: 'warning', label: '需要复核' },
  high_risk: { color: 'error', label: '身份高风险' },
  unscored: { color: 'default', label: '未评分' },
}

const SOURCE_LABELS = {
  auto_crop: '自动裁脸',
  manual_crop: '手动裁剪',
  upload: '本地上传',
  generated: '标准身份照',
  legacy_full_reference: '整张定妆图',
}

function cropPosition(box) {
  if (!box) return '50% 40%'
  return `${Math.round((box.x + box.width / 2) * 100)}% ${Math.round((box.y + box.height / 2) * 100)}%`
}

export default function IdentityRiskPanel({ attempt, identities, candidateImageUrl, mediaUrl }) {
  const evaluation = attempt?.identity_evaluation || {}
  const scored = evaluation.characters || []
  const rows = (identities || []).map((identity) => {
    const result = scored.find((item) => item.character_asset_id === identity.character_asset_id)
    return { identity, result, risk: result?.risk || 'unscored' }
  })
  if (!rows.length) return null

  return (
    <section className="identity-risk" aria-label="候选分镜身份相似度">
      <div className="identity-risk__header">
        <div>
          <div style={{ fontFamily: 'Georgia, serif', fontSize: 13 }}>Face Match / 身份复核</div>
          <div style={{ color: '#96919a', fontSize: 10, marginTop: 2 }}>
            机器分数只用于提醒，最终通过权仍由导演决定
          </div>
        </div>
        <Tag color={evaluation.status === 'scored' ? 'processing' : 'default'}>
          {evaluation.status === 'scored' ? 'SFace 已评分' : '未评分'}
        </Tag>
      </div>
      <div className="identity-risk__grid">
        {rows.map(({ identity, result, risk }) => {
          const meta = RISK_META[risk] || RISK_META.unscored
          return (
            <article className="identity-risk-card" data-risk={risk} key={identity.character_asset_id}>
              <div className="identity-risk-card__image" title="身份底片">
                <img src={mediaUrl(identity.reference_image_url)} alt={`${identity.character_name} 身份底片`} />
              </div>
              <div className="identity-risk-card__image" title="候选画面人脸区域">
                {candidateImageUrl ? (
                  <img
                    src={mediaUrl(candidateImageUrl)}
                    alt={`${identity.character_name} 候选人脸`}
                    style={{ objectPosition: cropPosition(result?.candidate_face) }}
                  />
                ) : null}
              </div>
              <div style={{ minWidth: 0 }}>
                <div className="identity-risk-card__name">{identity.character_name}</div>
                <div className="identity-risk-card__detail">
                  v{identity.reference_version || 0} · {SOURCE_LABELS[identity.reference_source_type] || identity.reference_source_type}
                </div>
                <div style={{ marginTop: 5 }}>
                  <Tag color={meta.color} style={{ margin: 0 }}>{meta.label}</Tag>
                  <span style={{ marginLeft: 6, color: '#ded8cf', font: '600 11px Consolas, monospace' }}>
                    {typeof result?.similarity === 'number' ? result.similarity.toFixed(3) : '—'}
                  </span>
                </div>
              </div>
            </article>
          )
        })}
      </div>
      {evaluation.warnings?.length ? (
        <div style={{ padding: '0 10px 10px', color: '#d6ad72', fontSize: 10 }}>
          {evaluation.warnings.includes('face_model_unavailable')
            ? '本地人脸模型未就绪，本候选需要完全人工复核。'
            : evaluation.warnings.includes('candidate_face_missing')
              ? '候选中没有为每位角色找到独立清晰的人脸，请重点复核。'
              : '身份自动评分失败，请人工复核。'}
        </div>
      ) : null}
    </section>
  )
}
