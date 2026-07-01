import type React from 'react'
import { Alert, Table, Tag } from 'antd'

type GuideSection = {
  id: string
  title: string
  eyebrow: string
  summary: string
}

type FlowStep = {
  title: string
  description: string
}

const guideSections: GuideSection[] = [
  { id: 'overview', title: '主流程一图看懂', eyebrow: '0', summary: '剧本、分镜、生成出片三阶段主线。' },
  { id: 'interface', title: '登录与认识界面', eyebrow: '1', summary: '全站导航、顶部流程、头像与任务中心。' },
  { id: 'project', title: '创建项目', eyebrow: '2', summary: '填写项目名称、视觉风格、视频风格和比例。' },
  { id: 'chapter', title: '录入章节剧本', eyebrow: '3', summary: '在项目工作台创建章节并粘贴剧本原文。' },
  { id: 'extract', title: '一键提取分镜并自动准备', eyebrow: '4', summary: '拆镜头、识别资产对白、生成缺失资产图。' },
  { id: 'prepare', title: '分镜准备与确认', eyebrow: '5', summary: '校对基础信息、镜头语言、资产与对白。' },
  { id: 'studio', title: '分镜工作室生成视频', eyebrow: '6', summary: '设置关键帧、提示词、参数，生成并选片。' },
  { id: 'assets', title: '资产管理与图片编辑', eyebrow: '7', summary: '管理角色、场景、道具、服装等素材。' },
  { id: 'quickstart', title: '一条最短上手路径', eyebrow: '8', summary: '按最短主线完成从剧本到素材下载。' },
]

const flowSteps: FlowStep[] = [
  { title: '剧本', description: '建项目、建章节、粘贴剧本原文' },
  { title: '分镜', description: '拆分镜、确认资产对白、补镜头信息' },
  { title: '生成出片', description: '出关键帧、改提示词、生成视频、选片下载' },
]

const quickSteps: FlowStep[] = [
  { title: '建项目', description: '选好视觉 / 视频风格与视频比例' },
  { title: '建章节 · 粘贴剧本', description: '把整段剧本贴进「章节内容」' },
  { title: '一键提取分镜并自动准备', description: 'AI 自动拆镜头，并准备资产与台词' },
  { title: '逐镜准备与确认', description: '确认资产 / 对白 / 基础信息，推进到准备完成' },
  { title: '进工作室生成视频', description: '检查关键帧、提示词和参数后生成视频' },
  { title: '选片下载', description: '在结果区选用满意视频并下载成片素材' },
]

const projectFields = [
  { key: 'name', field: '项目名称 *', detail: '给短剧起一个清晰名称，例如「东坡盼荔」。' },
  { key: 'description', field: '项目简介', detail: '用 80-120 字说明题材、风格和大致时长。' },
  { key: 'visual', field: '视觉风格 *', detail: '先选大方向画风，例如「现实」。' },
  { key: 'video', field: '视频风格 *', detail: '在画风下选择具体风格，例如「真人古装」。' },
  { key: 'seed', field: '全局种子值', detail: '固定后可让全片画面更统一，不熟悉时保留默认值。' },
  { key: 'ratio', field: '默认视频比例', detail: '可选 16:9 或 9:16，也可后续按镜头单独调整。' },
  { key: 'inherit', field: '强制继承风格', detail: '建议开启，让章节默认沿用项目统一风格。' },
]

const chapterStates = [
  { key: 'raw', status: '待录入原文', meaning: '还没粘贴剧本。', action: '编辑原文' },
  { key: 'extract', status: '待提取分镜', meaning: '已有剧本，但还没拆成镜头。', action: '提取分镜并自动准备' },
  { key: 'prepare', status: '待准备镜头', meaning: '镜头已拆好，还需要确认信息。', action: '进入分镜列表或分镜编辑页' },
  { key: 'shoot', status: '可进入拍摄', meaning: '分镜已具备后续生成条件。', action: '进入分镜工作室' },
]

const screenshots = [
  { src: '/guide/guide-shot-000.jpg', caption: '图 01 项目列表（主页面）' },
  { src: '/guide/guide-shot-001.jpg', caption: '图 02 新建项目弹窗' },
  { src: '/guide/guide-shot-002.jpg', caption: '图 03 新建章节弹窗' },
  { src: '/guide/guide-shot-003.jpg', caption: '图 04 项目工作台 · 章节列表' },
  { src: '/guide/guide-shot-004.jpg', caption: '图 05 项目工作台 · 仪表盘' },
  { src: '/guide/guide-shot-005.jpg', caption: '图 06 一键提取 · 积分确认弹窗' },
  { src: '/guide/guide-shot-006.jpg', caption: '图 07 分镜列表页' },
  { src: '/guide/guide-shot-007.jpg', caption: '图 08 分镜编辑页 · 基础信息' },
  { src: '/guide/guide-shot-008.jpg', caption: '图 09 分镜编辑页 · 提取确认' },
  { src: '/guide/guide-shot-009.jpg', caption: '图 10 分镜工作室 · 总览' },
  { src: '/guide/guide-shot-010.jpg', caption: '图 11 工作室 · 视频生成参数' },
  { src: '/guide/guide-shot-011.jpg', caption: '图 12 工作室 · 生成视频' },
  { src: '/guide/guide-shot-012.jpg', caption: '图 13 工作室 · 批量生成与下载' },
  { src: '/guide/guide-shot-013.jpg', caption: '图 14 工作室 · 视频提示词预览' },
  { src: '/guide/guide-shot-014.jpg', caption: '图 15 资产管理 · 资产库' },
  { src: '/guide/guide-shot-015.jpg', caption: '图 16 资产编辑 · 图片编辑' },
]

/**
 * 创作指引页：把 PDF 操作说明还原成产品内可阅读的图文页面。
 * 页面独立于业务数据，只承担全局帮助与主流程说明职责。
 */
const CreationGuidePage: React.FC = () => {
  return (
    <div className="h-full min-h-0 overflow-y-auto bg-slate-50">
      <div className="mx-auto flex w-full max-w-7xl gap-5 px-4 py-5 lg:px-6">
        <aside className="hidden lg:block">
          <nav className="fixed left-6 top-5 z-20 max-h-[calc(100vh-40px)] w-64 overflow-y-auto rounded-md border border-slate-200 bg-white p-3 shadow-sm">
            <div className="mb-2 px-2 text-xs font-semibold text-slate-500">创作指引目录</div>
            <div className="space-y-1">
              {guideSections.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="block rounded px-2 py-2 text-sm text-slate-600 transition hover:bg-blue-50 hover:text-blue-700"
                >
                  <span className="mr-2 font-semibold text-blue-700">{section.eyebrow}</span>
                  {section.title}
                </a>
              ))}
            </div>
          </nav>
        </aside>

        <main className="min-w-0 flex-1 lg:ml-72">
          <section className="mb-5 rounded-md border border-slate-200 bg-white px-5 py-6 shadow-sm md:px-8">
            <div className="border-b border-blue-200 pb-5 text-center">
              <h1 className="mb-2 text-3xl font-bold text-blue-900">创作指引</h1>
              <p className="mb-1 text-base font-semibold text-slate-700">核心创作流程 · 操作说明</p>
              <p className="text-sm text-slate-500">从「剧本」到「成片」的完整创作路径</p>
            </div>
            <div className="mt-6 grid gap-3 md:grid-cols-3">
              {flowSteps.map((step, index) => (
                <div key={step.title} className="relative">
                  {index < flowSteps.length - 1 && (
                    <div className="absolute left-[calc(50%+48px)] right-[calc(-50%+48px)] top-7 hidden h-px bg-blue-200 md:block" />
                  )}
                  <div className="relative z-10 flex h-full min-h-[150px] flex-col rounded-md border border-blue-100 bg-blue-50 px-4 py-4">
                    <div className="mb-3 flex items-center gap-3">
                      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-700 text-sm font-semibold text-white">
                        {index + 1}
                      </span>
                      <span className="text-sm font-semibold text-blue-900">阶段 {index + 1}</span>
                    </div>
                    <div className="text-lg font-semibold text-slate-900">{step.title}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-600">{step.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <article className="space-y-5">
            <GuideBlock id="overview" number="0" title="主流程一图看懂">
              <p>一部短剧的制作分为三个串行阶段，界面全程围绕这条主线做「下一步」引导。</p>
              <div className="overflow-hidden rounded-md border border-slate-200">
                <Table
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '阶段', dataIndex: 'stage', width: 120 },
                    { title: '主要页面', dataIndex: 'page' },
                    { title: '你在这里做什么', dataIndex: 'work' },
                  ]}
                  dataSource={[
                    { key: 'script', stage: '① 剧本', page: '项目列表 → 项目工作台「章节」', work: '建项目、建章节、粘贴剧本原文' },
                    { key: 'shot', stage: '② 分镜', page: '分镜列表 + 分镜编辑页', work: '一键拆分镜、确认资产/对白、补镜头信息' },
                    { key: 'video', stage: '③ 生成出片', page: '分镜工作室', work: '出关键帧、改提示词、生成视频、选片下载成片' },
                  ]}
                />
              </div>
              <Alert
                type="warning"
                showIcon
                message="关键心智"
                description="每一章、每个镜头都有一个准备状态。系统会根据状态在卡片和顶部算出下一步；跟着每页的蓝色主按钮走，就是推荐路径。"
              />
            </GuideBlock>

            <GuideBlock id="interface" number="1" title="登录与认识界面">
              <p>登录后进入「主页面」，也就是所有短剧项目的列表。先确认全站四个常用位置：</p>
              <ul className="list-disc space-y-2 pl-5">
                <li><strong>左侧菜单栏：</strong>项目列表、资产管理、提示词模板、模型管理、积分明细；管理员还能看到用户管理。</li>
                <li><strong>顶部按钮：</strong>进入项目后按「主页面 / 项目工作台 / 分镜列表 / 分镜工作室」逐步点亮。</li>
                <li><strong>右上角头像：</strong>查看积分、修改密码、退出登录。</li>
                <li><strong>左下角任务中心：</strong>查看拆分镜、生成图片、生成视频等 AI 任务进度。</li>
              </ul>
              <Alert type="info" showIcon message="开始前先确认模型管理已配置可用模型，并且账户有足够积分。" />
            </GuideBlock>

            <GuideBlock id="project" number="2" title="创建项目">
              <p>在主页面点右上角「新建项目」，填写项目信息后点「创建并进入」，系统会带你进入项目工作台。</p>
              <Figure {...screenshots[0]} />
              <Figure {...screenshots[1]} />
              <div className="overflow-hidden rounded-md border border-slate-200">
                <Table
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '填什么', dataIndex: 'field', width: 160 },
                    { title: '怎么填', dataIndex: 'detail' },
                  ]}
                  dataSource={projectFields}
                />
              </div>
              <p>项目卡片会展示「现在到哪一步、下一步该干嘛」，并用「剧本 → 分镜 → 资产 → 视频」进度条提示整体状态。</p>
            </GuideBlock>

            <GuideBlock id="chapter" number="3" title="录入章节剧本（项目工作台）">
              <p>项目工作台顶部有「章节 / 演员 / 角色 / 场景 / 道具 / 服装 / 仪表盘」等标签。主线流程先使用「章节」。</p>
              <Figure {...screenshots[2]} />
              <Figure {...screenshots[3]} />
              <div className="overflow-hidden rounded-md border border-slate-200">
                <Table
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '当前状态', dataIndex: 'status', width: 140 },
                    { title: '是什么意思', dataIndex: 'meaning' },
                    { title: '该点的按钮', dataIndex: 'action' },
                  ]}
                  dataSource={chapterStates}
                />
              </div>
              <Figure {...screenshots[4]} />
              <p>仪表盘可以总览未完成章节、待确认分镜、已就绪分镜和生成中分镜，也会把当前最该做的下一步放在动态摘要里。</p>
            </GuideBlock>

            <GuideBlock id="extract" number="4" title="一键提取分镜并自动准备">
              <p>在章节列表点「提取分镜并自动准备」，系统会把剧本拆成分镜、识别每个镜头的资产和台词，并自动关联或新建缺失资产。</p>
              <Figure {...screenshots[5]} />
              <p>确认积分后任务会在后台运行，可在任务中心查看进度或取消。提取完成后进入分镜列表。</p>
              <Figure {...screenshots[6]} />
              <Alert
                type="error"
                showIcon
                message="注意"
                description="如果这一集已经有分镜，就不能再次一键提取；要重新提取，需要先删除现有分镜。"
              />
            </GuideBlock>

            <GuideBlock id="prepare" number="5" title="分镜准备与确认（分镜编辑页）">
              <p>在分镜列表点「编辑」进入分镜编辑页。目标是把每个镜头的信息核对好，让它达到可以生成视频的状态。</p>
              <Figure {...screenshots[7]} />
              <p>基础信息里重点确认标题、剧本摘录、景别、机位、运镜、时长和动作拍点。动作拍点保留 2-4 条即可。</p>
              <Figure {...screenshots[8]} />
              <p>提取确认里检查场景、角色、道具、服装和对白。待确认候选需要关联或忽略；纯画面镜头可标记「无需提取」。</p>
              <Alert type="success" showIcon message="效率建议" description="先把所有镜头逐个确认好，再统一进入分镜工作室批量生成视频。" />
            </GuideBlock>

            <GuideBlock id="studio" number="6" title="分镜工作室（生成画面与视频）">
              <p>分镜工作室负责真正出片：左栏选镜头，中间看视频结果，右栏配置关键帧、参考图、生成参数和视频生成。</p>
              <Figure {...screenshots[9]} />
              <Figure {...screenshots[10]} />
              <p>在「生成参数」里设置景别、角度、运镜、时长、视频比例和分辨率；在「视频生成」里选择参考图、模型和清晰度后发起生成。</p>
              <Figure {...screenshots[11]} />
              <Figure {...screenshots[12]} />
              <p>批量生成会先做视频准备度检查，未通过的镜头会自动跳过并给出诊断。生成完成后，在结果区点「√」选用满意视频，再一键下载。</p>
              <Figure {...screenshots[13]} />
              <p>视频提示词已经由 Agent 自动整理，包含镜头标题、剧本摘录、动作节拍、项目风格、资产设定和连续性上下文；需要精修时再展开修改。</p>
            </GuideBlock>

            <GuideBlock id="assets" number="7" title="资产管理与图片编辑">
              <p>资产管理用于维护全局素材库，包含演员、角色、场景、道具、服装。分镜提取时 AI 自动建的资产也会出现在这里。</p>
              <Figure {...screenshots[14]} />
              <Figure {...screenshots[15]} />
              <p>资产编辑页支持用文字描述改图，也支持在描述中输入「@」引用其他资产参与融合生图。主要角色和主场景越统一，后续视频越稳定。</p>
            </GuideBlock>

            <GuideBlock id="quickstart" number="8" title="一条最短上手路径">
              <div className="space-y-0">
                {quickSteps.map((step, index) => (
                  <div key={step.title} className="relative pl-12">
                    {index < quickSteps.length - 1 && (
                      <div className="absolute left-4 top-9 h-full w-px bg-blue-200" />
                    )}
                    <div className="absolute left-0 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-full border border-blue-200 bg-white text-sm font-semibold text-blue-700">
                      {index + 1}
                    </div>
                    <div className="pb-4">
                      <div className="rounded-md border border-blue-100 bg-blue-50 px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <Tag color="blue">步骤 {index + 1}</Tag>
                          <h3 className="m-0 text-base font-semibold text-slate-900">{step.title}</h3>
                        </div>
                        <p className="mt-1 text-sm text-slate-600">{step.description}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </GuideBlock>
          </article>
        </main>
      </div>
    </div>
  )
}

/**
 * 指引正文段落：统一章节锚点、编号和标题样式。
 */
const GuideBlock: React.FC<{
  id: string
  number: string
  title: string
  children: React.ReactNode
}> = ({ id, number, title, children }) => (
  <section id={id} className="scroll-mt-4 rounded-md border border-slate-200 bg-white px-5 py-5 shadow-sm md:px-8">
    <div className="mb-4 border-b border-slate-200 pb-3">
      <div className="text-sm font-semibold text-blue-700">第 {number} 节</div>
      <h2 className="m-0 text-2xl font-bold text-blue-900">{title}</h2>
    </div>
    <div className="space-y-4 text-[15px] leading-7 text-slate-700">{children}</div>
  </section>
)

/**
 * 产品截图展示块：复用 PDF 中提取的图片并提供稳定尺寸与说明。
 */
const Figure: React.FC<{ src: string; caption: string }> = ({ src, caption }) => (
  <figure className="rounded-md border border-slate-200 bg-slate-50 p-3">
    <img src={src} alt={caption} className="max-h-[520px] w-full rounded border border-slate-100 bg-white object-contain" loading="lazy" />
    <figcaption className="mt-2 text-center text-xs text-slate-500">{caption}</figcaption>
  </figure>
)

export default CreationGuidePage
