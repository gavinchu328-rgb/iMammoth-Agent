import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { maskReportUrlsInMarkdown, resolveLinkChildren } from '../utils/reportLinkLabel'

interface Props {
  children: string
  className?: string
}

export default function AssistantMarkdown({ children, className }: Props) {
  const content = maskReportUrlsInMarkdown(children)

  return (
    <div className={className}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children: linkChildren }) => {
            const hrefStr = href ?? ''
            const raw = String(linkChildren ?? '')
            const label = resolveLinkChildren(hrefStr, raw)
            return (
              <a
                href={hrefStr}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#4BA4F8] underline decoration-[#4BA4F8]/40 underline-offset-2 hover:decoration-[#4BA4F8]"
              >
                {label}
              </a>
            )
          },
        }}
      >
        {content}
      </Markdown>
    </div>
  )
}
