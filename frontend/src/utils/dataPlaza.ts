export function dataPlazaPath(project?: string | null, category?: string | null): string {
  const params = new URLSearchParams()
  if (project && project !== '全部') params.set('project', project)
  if (category && category !== '全部') params.set('category', category)
  const qs = params.toString()
  return qs ? `/data?${qs}` : '/data'
}
