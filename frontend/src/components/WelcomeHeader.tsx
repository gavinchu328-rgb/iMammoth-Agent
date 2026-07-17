export default function WelcomeHeader() {
  return (
    <div className="animate-slide-up relative mt-2 mb-4 flex h-[100px] w-full items-center justify-center text-center md:h-[150px] md:max-w-[880px]">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: 'url(/huixiang.png)',
          backgroundSize: '100% 100%',
          opacity: 0.38,
          filter: 'blur(50px)',
        }}
      />
      <h1 className="relative z-10 inline-flex items-center justify-center gap-2 bg-linear-to-r from-slate-900 via-slate-700 to-slate-900 bg-clip-text text-xl leading-tight font-extrabold text-transparent md:text-[30px]">
        <div className="relative shrink-0" style={{ width: 80, height: 80 }}>
          <img
            alt="猛犸智能体"
            className="relative z-10 h-full w-full object-contain"
            draggable={false}
            src="/huixiang.png"
          />
        </div>
        <span className="inline-flex items-center">
          你好，我是{' '}
          <span className="bg-linear-to-r from-[#2563EB] to-[#60A5FA] bg-clip-text text-transparent">
            &nbsp;猛犸智能体
          </span>
        </span>
      </h1>
    </div>
  )
}
