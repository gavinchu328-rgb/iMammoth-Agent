/** 将 AI4Drug 报告等长链接转为可读标签 */

const REPORT_SEGMENT_LABELS: Array<{ test: RegExp; label: string }> = [
  { test: /target_discovery/i, label: '靶点发现报告' },
  { test: /protein_acquisition/i, label: '蛋白获取报告' },
  { test: /pocket_prediction/i, label: '口袋预测报告' },
  { test: /molecule_design/i, label: '分子设计报告' },
  { test: /conformer_generation/i, label: '构象生成报告' },
  { test: /receptor_preparation/i, label: '受体准备报告' },
  { test: /ligand_preparation/i, label: '配体准备报告' },
  { test: /docking_box/i, label: '对接盒配置报告' },
  { test: /molecular_docking/i, label: '分子对接报告' },
  { test: /molecule_evaluation/i, label: 'ADMET 评估报告' },
  { test: /retrosynthesis/i, label: '逆合成分析报告' },
]

function isUrlLike(text: string): boolean {
  const t = text.trim()
  return /^https?:\/\//i.test(t) || (t.includes('/') && t.length > 48)
}

export function reportLinkLabel(href: string): string {
  const lower = href.toLowerCase()
  if (lower.includes('ai4drug-reports')) {
    for (const { test, label } of REPORT_SEGMENT_LABELS) {
      if (test.test(href)) return label
    }
    return '查看分析报告'
  }
  if (/\.(pdb|pdbqt|mol2|sdf)$/i.test(href)) {
    const name = href.replace(/\/+$/, '').split('/').pop()
    return name || '下载结构文件'
  }
  return '打开链接'
}

/** 解析链接展示文字：已有中文标签则保留，裸 URL 则替换 */
export function resolveLinkChildren(href: string, children: string): string {
  const text = children.trim()
  if (!text || isUrlLike(text)) return reportLinkLabel(href)
  return children
}

/** 将正文中的裸报告 URL 转为 [标签](url) */
export function maskReportUrlsInMarkdown(text: string): string {
  return text.replace(
    /<?(https?:\/\/[^\s)>]+(?:ai4drug-reports)[^\s)>]*)>?/gi,
    (url) => {
      const clean = url.replace(/^<|>$/g, '')
      return `[${reportLinkLabel(clean)}](${clean})`
    },
  )
}
