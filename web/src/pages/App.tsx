import React, { useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import DeepSeekLogo from '../assets/DeepSeek.jpg'

// Types
interface TopItem { label: string; confidence: number }
interface Prediction { label: string; confidence: number; top?: TopItem[] }
interface Guide {
  short_description?: string
  causes?: string[]
  prevention?: string[]
  treatment?: string[]
  risk_factors?: string[]
}

type ChatItem = { role: 'user' | 'assistant', content: string, guide?: Guide }

function App() {
  const fileRef = useRef<HTMLInputElement>(null)
  const aboutFocusRef = useRef<HTMLDivElement | null>(null)
  const [imgPreview, setImgPreview] = useState<string | null>(null)
  const [predicting, setPredicting] = useState(false)
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [showPredictionDetails, setShowPredictionDetails] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [chat, setChat] = useState<ChatItem[]>([])
  const [replying, setReplying] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [isDark, setIsDark] = useState(false)
  const [showSplash, setShowSplash] = useState(true)
  const [showDirectUse, setShowDirectUse] = useState(false)
  const [showDiseases, setShowDiseases] = useState(false)
  const [showAbout, setShowAbout] = useState(false)
  // Show full overlay only for initial auto-overview after prediction
  const [overlayForAuto, setOverlayForAuto] = useState(false)

  useEffect(() => {
    const root = document.documentElement
    if (isDark) root.classList.add('dark')
    else root.classList.remove('dark')
  }, [isDark])

  useEffect(() => {
    const t = setTimeout(() => setShowSplash(false), 1900)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    const body = document.body
    if (showSplash || showAbout) body.classList.add('no-scroll')
    else body.classList.remove('no-scroll')
  }, [showSplash, showAbout])

  const onPick = () => fileRef.current?.click()

  const onFile = (f?: File) => {
    const file = f ?? fileRef.current?.files?.[0]
    if (!file) return
    const url = URL.createObjectURL(file)
    setImgPreview(url)
    setPrediction(null)
  }

  const clearFile = () => {
    setImgPreview(null)
    setPrediction(null)
    if (fileRef.current) (fileRef.current as HTMLInputElement).value = ''
  }

  const handleDrop: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files?.[0]
    if (f) onFile(f)
  }

  // Downscale image client-side to reduce upload and server decode time
  const downscaleImage = async (file: File, maxDim = 1024, mime = 'image/jpeg', quality = 0.85): Promise<Blob> => {
    try {
      const bitmap = await createImageBitmap(file)
      let { width, height } = bitmap
      const scale = Math.min(1, maxDim / Math.max(width, height))
      const w = Math.max(1, Math.round(width * scale))
      const h = Math.max(1, Math.round(height * scale))
      const canvas = document.createElement('canvas')
      canvas.width = w; canvas.height = h
      const ctx = canvas.getContext('2d')
      if (!ctx) return file
      ctx.imageSmoothingEnabled = true
      ;(ctx as any).imageSmoothingQuality = 'high'
      ctx.drawImage(bitmap, 0, 0, w, h)
      bitmap.close()
      const blob: Blob = await new Promise(resolve => canvas.toBlob((b: Blob | null) => resolve(b || file), mime, quality))
      return blob
    } catch {
      return file
    }
  }

  const runPredict = async () => {
    const f = fileRef.current?.files?.[0]
    if (!f) return alert('Please choose an image first.')
    setPredicting(true)
    setShowPredictionDetails(false)
    let predicted: Prediction | null = null
    try {
      const form = new FormData()
      const resized = await downscaleImage(f, 1024, 'image/jpeg', 0.85)
      const upload = resized instanceof Blob ? new File([resized], 'upload.jpg', { type: 'image/jpeg' }) : f
      form.append('image', upload)
      const { data } = await axios.post('/api/vision/predict/', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      predicted = data

      // Auto fetch concise guide ONCE and show overlay during this phase
      setReplying(true)
      setOverlayForAuto(true)
      try {
        const history = chat.map(m => ({ role: m.role, content: m.guide ? JSON.stringify(m.guide) : m.content }))
        const payload: any = {
          message: 'Provide a concise guide for the predicted disease.',
          site: 'Leaf Vision',
          referrer: window.location.origin,
          disease: data.label,
          confidence: data.confidence,
          history,
          force_json: true,
        }
        const resp = await axios.post('/api/chat/', payload)
        if (resp.data?.guide) {
          setChat((c: ChatItem[]) => [...c, { role: 'assistant', content: 'Overview', guide: resp.data.guide as Guide }])
        } else if (resp.data?.reply) {
          setChat((c: ChatItem[]) => [...c, { role: 'assistant', content: String(resp.data.reply) }])
        }
      } catch (e: any) {
        setChat((c: ChatItem[]) => [...c, { role: 'assistant', content: e?.response?.data?.error || 'Could not fetch overview.' }])
      } finally {
        setOverlayForAuto(false)
        setReplying(false)
        if (predicted) setPrediction(predicted)
        setShowPredictionDetails(true)
      }
    } catch (e: any) {
      alert(e?.response?.data?.error || e.message)
    } finally {
      setPredicting(false)
    }
  }

  const sendChat = async () => {
    if (!chatInput) return
    setReplying(true)
    const msg = chatInput
    setChat((c: ChatItem[]) => [...c, { role: 'user', content: msg }])
    setChatInput('')
    try {
      const includeDisease = !!prediction
      const history = chat.map(m => ({ role: m.role, content: m.guide ? JSON.stringify(m.guide) : m.content }))
      const payload: any = {
        message: msg,
        site: 'Leaf Vision',
        referrer: window.location.origin,
        history,
      }
      if (includeDisease && prediction) {
        payload.disease = prediction.label
        payload.confidence = prediction.confidence
      }
      const { data } = await axios.post('/api/chat/', payload)
      if (data.guide) {
        setChat((c: ChatItem[]) => [...c, { role: 'assistant', content: 'Overview', guide: data.guide as Guide }])
      } else {
        setChat((c: ChatItem[]) => [...c, { role: 'assistant', content: data.reply }])
      }
    } catch (e: any) {
      setChat((c: ChatItem[]) => [...c, { role: 'assistant', content: e?.response?.data?.error || e.message }])
    } finally {
      // For manual chats we do NOT show overlay; only button spinner is visible
      setReplying(false)
    }
  }

  const Section = ({ title, items }: { title: string, items?: string[] }) => {
    if (!items || items.length === 0) return null
    return (
      <div>
        <h4 className="font-semibold mb-1">{title}</h4>
        <ul className="list-disc ml-5 text-sm space-y-1">
          {items.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      </div>
    )
  }

  const renderGuide = (g: Guide) => (
    <div className="space-y-4">
      {g.short_description && (
        <div>
          <h4 className="font-semibold mb-1 text-gradient">Overview</h4>
          <p className="text-sm leading-relaxed">{g.short_description}</p>
        </div>
      )}
      <Section title="Causes" items={g.causes} />
      <Section title="Prevention" items={g.prevention} />
      <Section title="Treatment" items={g.treatment} />
      <Section title="Risk factors" items={g.risk_factors} />
    </div>
  )

  const Header = useMemo(() => (
    <header className="sticky top-0 z-20 overflow-hidden backdrop-blur bg-white/60 dark:bg-slate-900/50 border-b border-white/40 dark:border-slate-800">
      {/* existing decorative elements remain unchanged */}
      <div className="w-full px-3 sm:px-4 py-3 relative flex items-center justify-between">
        <div className="inline-flex items-center gap-3">
          <span className="relative inline-flex items-center justify-center w-10 h-10 rounded-2xl shadow-xl ring-1 ring-black/5 overflow-hidden logo-animate">
            <span className="absolute inset-0 bg-gradient-to-br from-emerald-400 to-teal-500" />
            <svg className="relative w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M12 2c4 2 8 6 8 10s-4 8-8 10C8 20 4 16 4 12S8 4 12 2z"/>
            </svg>
          </span>
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-gradient">Leaf Vision</h1>
            <p className="text-sm sm:text-base text-gray-700 dark:text-gray-300 mt-0.5">Detect leaf diseases with visual AI and get clear, actionable guidance.</p>
          </div>
        </div>
        <nav className="flex items-center gap-3">
          <button onClick={() => setShowAbout(true)} className="btn-3d btn-secondary px-4 py-2 rounded-full text-sm">About</button>
          <button onClick={() => setIsDark(v => !v)} className="btn-3d btn-secondary px-3 py-2 rounded-md" aria-label="Toggle theme">
            {isDark ? (
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M6.76 4.84l-1.8-1.79 1.41-1.41 1.79 1.8-1.4 1.4zm10.48 14.32l1.79 1.8 1.41-1.41-1.8-1.79-1.4 1.4zM12 4V1h0v3zm0 19v-3h0v3zM4 12H1v0h3zm19 0h-3v0h3zM6.76 19.16l-1.4 1.4-1.79-1.8 1.41-1.41 1.78 1.81zM17.24 4.84l1.4-1.4 1.8 1.79-1.41 1.41-1.79-1.8zM12 6a6 6 0 100 12A6 6 0 0012 6z"/></svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
            )}
          </button>
        </nav>
      </div>
    </header>
  ), [isDark])

  const TypingDots: React.FC = () => (
    <span aria-label="Assistant is typing" className="inline-flex items-center">
      <svg className="w-6 h-2 text-gray-500" viewBox="0 0 24 8" fill="currentColor" aria-hidden>
        <circle cx="4" cy="4" r="3">
          <animate attributeName="opacity" values="0.2;1;0.2" dur="1s" repeatCount="indefinite" begin="0s" />
        </circle>
        <circle cx="12" cy="4" r="3">
          <animate attributeName="opacity" values="0.2;1;0.2" dur="1s" repeatCount="indefinite" begin="0.2s" />
        </circle>
        <circle cx="20" cy="4" r="3">
          <animate attributeName="opacity" values="0.2;1;0.2" dur="1s" repeatCount="indefinite" begin="0.4s" />
        </circle>
      </svg>
    </span>
  )

  const ChatCard = useMemo(() => (
    <section className="flex flex-col min-h-0 reveal-up relative">
      <div className="overflow-y-auto h-[55dvh] sm:h-[60dvh] md:h-[68dvh] space-y-3 p-3 glass-card light-panel rounded-xl scroll-touch overscroll-contain">
        {chat.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'text-right' : ''}>
            <div className={`inline-block max-w-[85%] p-3 rounded-2xl text-sm lift-3d ${m.role === 'user' ? 'bg-blue-600 text-white' : 'bg-white text-gray-900 border border-gray-200'}`}>
              {m.guide ? renderGuide(m.guide) : <div className="whitespace-pre-line">{m.content}</div>}
            </div>
          </div>
        ))}
        {/* Messenger-like typing bubble for manual replies */}
        {replying && !overlayForAuto && (
          <div>
            <div className="inline-block max-w-[85%] p-3 rounded-2xl text-sm bg-white text-gray-900 border border-gray-200">
              <TypingDots />
            </div>
          </div>
        )}
      </div>
      <div className="mt-3 flex gap-2">
        <input value={chatInput} onChange={e => setChatInput(e.target.value)} placeholder="Ask about causes, prevention, treatment, risk factors…" className="flex-1 border border-gray-200 rounded-full px-4 py-2 bg-white text-gray-900 placeholder:text-gray-400 shadow-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" />
        <button onClick={sendChat} disabled={replying} className="btn-3d btn-primary px-5 py-2 rounded-full disabled:opacity-50">
          {replying ? (
            <span className="inline-flex items-center justify-center">
              <svg className="w-5 h-5 animate-spin text-white" viewBox="0 0 24 24" fill="none" aria-hidden>
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
            </span>
          ) : 'Send'}
        </button>
      </div>
      {/* Overlay only for automatic overview */}
      {replying && overlayForAuto && (
        <div className="absolute inset-0 z-20 bg-white/40 dark:bg-slate-900/30 backdrop-blur-sm flex items-center justify-center rounded-xl">
          <div className="flex items-center gap-3 text-gray-700 dark:text-gray-200">
            <svg className="w-6 h-6 animate-spin text-emerald-600" viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            <span className="text-sm font-medium">Analyzing…</span>
          </div>
        </div>
      )}
    </section>
  ), [chat, chatInput, replying, overlayForAuto])

  const prettyLabel = (s: string) => s.replace(/___/g, ' ').replace(/__/g, ' ').replace(/_/g, ' ')

  useEffect(() => {
    // Focus about modal for accessibility and scroll to top inside modal
    if (showAbout && aboutFocusRef.current) {
      aboutFocusRef.current.scrollTop = 0
      aboutFocusRef.current.focus()
    }
  }, [showAbout])

  return (
    <div className="min-h-dvh animated-bg app-bg dark:bg-gradient-to-br dark:from-slate-950 dark:via-slate-900 dark:to-slate-900 contain-paint">
      {showSplash && (
        <div className="splash-screen">
          <div className="flex flex-col items-center">
            <div className="splash-logo">
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M12 2c4 2 8 6 8 10s-4 8-8 10C8 20 4 16 4 12S8 4 12 2z"/>
              </svg>
            </div>
            <div className="splash-title">Leaf Vision</div>
          </div>
        </div>
      )}
      {/* Global leaf overlay bottom-left fixed */}
      <svg className="pointer-events-none fixed -bottom-10 -left-10 w-[360px] h-[360px] leaf-overlay" viewBox="0 0 256 256" fill="none" aria-hidden>
        <defs>
          <linearGradient id="g2b" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#22c55e"/><stop offset="100%" stopColor="#10b981"/>
          </linearGradient>
        </defs>
        <path d="M216 40c-56 8-96 32-120 56S52 156 40 216c60-12 120-20 168-64s28-84 8-112z" fill="url(#g2b)" />
        <path d="M88 168c24-40 72-88 128-112" stroke="#065f46" strokeOpacity="0.35" strokeWidth="6" strokeLinecap="round"/>
      </svg>
      {Header}
      <main className="w-full scroll-touch">
        <div className="w-full px-3 sm:px-4 py-3 grid md:grid-cols-2 gap-4">
          {/* Left column */}
          <div className="flex flex-col gap-6 contain-paint">
            {/* Diseases card with Direct Use (collapsible) */}
            <section className="space-y-4 reveal-up">
              {/* this wrapper renders the diseases card only */}
              <div className="gradient-frame reveal-up">
                <div className="glass-card light-panel rounded-[0.95rem] p-4">
                  {/* existing collapsible header and content driven by showDiseases/showDirectUse */}
                  {/* We re-use the same block as defined in UploadCard previously */}
                  {/* Start inline: */}
                  <button onClick={() => setShowDiseases(v => !v)} aria-expanded={showDiseases} className="w-full flex items-center justify-between text-left">
                    <h3 className="font-semibold text-gradient flex items-center gap-2">
                      <svg className="w-5 h-5 text-emerald-500" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c4 2 8 6 8 10s-4 8-8 10C8 20 4 16 4 12S8 4 12 2z"/></svg>
                      Diseases from the model
                    </h3>
                    <svg className={`w-4 h-4 transition-transform ${showDiseases ? 'rotate-180' : ''}`} viewBox="0 0 20 20" fill="currentColor"><path d="M5.23 7.21a.75.75 0 011.06.02L10 10.939l3.71-3.71a.75.75 0 111.06 1.061l-4.24 4.24a.75.75 0 01-1.06 0L5.25 8.27a.75.75 0 01-.02-1.06z"/></svg>
                  </button>
                  <div className={`transition-[max-height,opacity] duration-500 ${showDiseases ? 'opacity-100' : 'opacity-0'} ${showDiseases ? '' : 'pointer-events-none'}`}
                       style={{ maxHeight: showDiseases ? 1000 : 0 }}>
                    {/* Grid of diseases (copied from previous) */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm mt-3">
                      {/* Corn */}
                      <div>
                        <div className="font-medium text-emerald-700">Corn</div>
                        <ul className="ml-4 mt-1 space-y-1">
                          <li className="px-2 py-1 rounded bg-emerald-50 text-emerald-700">Common Rust</li>
                          <li className="px-2 py-1 rounded bg-emerald-50/70 text-emerald-700">Gray Leaf Spot</li>
                          <li className="px-2 py-1 rounded bg-emerald-50/70 text-emerald-700">Healthy</li>
                          <li className="px-2 py-1 rounded bg-emerald-50/70 text-emerald-700">Leaf Blight</li>
                        </ul>
                      </div>
                      {/* Potato */}
                      <div>
                        <div className="font-medium text-teal-700">Potato</div>
                        <ul className="ml-4 mt-1 space-y-1">
                          <li className="px-2 py-1 rounded bg-teal-50 text-teal-700">Early Blight</li>
                          <li className="px-2 py-1 rounded bg-teal-50/70 text-teal-700">Healthy</li>
                          <li className="px-2 py-1 rounded bg-teal-50/70 text-teal-700">Late Blight</li>
                        </ul>
                      </div>
                      {/* Rice */}
                      <div>
                        <div className="font-medium text-sky-700">Rice</div>
                        <ul className="ml-4 mt-1 space-y-1">
                          <li className="px-2 py-1 rounded bg-sky-50 text-sky-700">Brown Spot</li>
                          <li className="px-2 py-1 rounded bg-sky-50/70 text-sky-700">Healthy</li>
                          <li className="px-2 py-1 rounded bg-sky-50/70 text-sky-700">Leaf Blast</li>
                        </ul>
                      </div>
                      {/* Wheat */}
                      <div>
                        <div className="font-medium text-amber-700">Wheat</div>
                        <ul className="ml-4 mt-1 space-y-1">
                          <li className="px-2 py-1 rounded bg-amber-50 text-amber-700">Brown Rust</li>
                          <li className="px-2 py-1 rounded bg-amber-50/70 text-amber-700">Healthy</li>
                          <li className="px-2 py-1 rounded bg-amber-50/70 text-amber-700">Yellow Rust</li>
                        </ul>
                      </div>
                      {/* Other */}
                      <div>
                        <div className="font-medium text-slate-700">Other</div>
                        <ul className="ml-4 mt-1 space-y-1">
                          <li className="px-2 py-1 rounded bg-slate-50 text-slate-700">Invalid</li>
                        </ul>
                      </div>
                    </div>

                    {/* Direct Use toggle + description */}
                    <div className="mt-3 text-sm text-gray-700">
                      <button onClick={() => setShowDirectUse(v => !v)} aria-expanded={showDirectUse} className="inline-flex items-center gap-2 text-emerald-700 hover:text-emerald-600 font-semibold">
                        <span>Direct Use</span>
                        <svg className={`w-4 h-4 transition-transform ${showDirectUse ? 'rotate-180' : ''}`} viewBox="0 0 20 20" fill="currentColor"><path d="M5.23 7.21a.75.75 0 011.06.02L10 10.939l3.71-3.71a.75.75 0 111.06 1.061l-4.24 4.24a.75.75 0 01-1.06 0L5.25 8.27a.75.75 0 01-.02-1.06z"/></svg>
                      </button>
                      {showDirectUse && (
                        <div className="mt-2">
                          <p className="leading-relaxed text-justify text-gradient-strong">This model can be used directly to classify images of crops to detect plant diseases. It is especially useful for precision farming, enabling users to monitor crop health and take early interventions based on the detected disease.</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Upload area BELOW the diseases card */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                className={`relative border-2 border-dashed rounded-xl p-6 glass-card light-panel ${dragOver ? 'border-emerald-400 bg-emerald-50/80' : ''}`}
              >
                <div className="flex items-center gap-3">
                  <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={() => onFile()} />
                  <button onClick={onPick} className="btn-3d btn-primary px-4 py-2">Upload Photo</button>
                  <button onClick={runPredict} disabled={predicting || !imgPreview} className="btn-3d px-4 py-2 bg-blue-600 text-white rounded-full disabled:opacity-50 hover:bg-blue-500">{predicting ? 'Analyzing…' : 'Predict'}</button>
                  <button onClick={clearFile} disabled={!imgPreview} className="btn-3d px-4 py-2 bg-rose-600 text-white rounded-full disabled:opacity-50 hover:bg-rose-500" aria-label="Remove selected image">Remove</button>
                </div>
                <p className="text-xs text-gray-600 mt-2">Drag & drop an image here, or click Upload Photo.</p>
                {imgPreview && (
                  <div className="mt-4 flex justify-center">
                    <img
                      src={imgPreview}
                      alt="preview"
                      loading="lazy"
                      decoding="async"
                      className="mx-auto max-h-96 max-w-full object-contain rounded-lg border border-white/50 shadow"
                    />
                  </div>
                )}
                {predicting && (
                  <div className="mt-4 flex flex-col items-center gap-3" aria-live="polite" aria-label="Analyzing image">
                    <div className="flex items-center gap-2 text-sm font-medium text-emerald-700">
                      <svg className="w-5 h-5 animate-spin text-emerald-600" viewBox="0 0 24 24" fill="none" aria-hidden>
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                      </svg>
                      <span>Analyzing image…</span>
                    </div>
                    <div className="relative w-48 h-2 rounded-full overflow-hidden bg-emerald-100 dark:bg-emerald-900/40">
                      <div className="absolute inset-y-0 left-0 w-1/3 rounded-full animate-loading-bar bg-gradient-to-r from-emerald-400 via-teal-400 to-sky-400" />
                    </div>
                  </div>
                )}

                {/* Prediction details below image (top-1 only) */}
                {prediction && showPredictionDetails && (
                  <div className="mt-4 glass-card light-panel rounded-xl p-4 border border-white/50 max-w-md mx-auto">
                    <h3 className="font-semibold text-gradient mb-2 text-center">Prediction Details</h3>
                    <div className="text-sm text-center">
                      <div className="font-medium">{prettyLabel(String(prediction.label))}</div>
                      <div className="text-gray-700">Confidence: {typeof prediction.confidence === 'number' ? prediction.confidence.toFixed(4) : String(prediction.confidence)}</div>
                    </div>
                    <p className="text-[11px] text-gray-500 mt-2 text-center">Ask in chat for causes, prevention, or treatment.</p>
                  </div>
                )}
              </div>
            </section>
          </div>
          {/* Right column */}
          {ChatCard}
        </div>
      </main>
      {showAbout && (
        <div className="about-backdrop" role="dialog" aria-modal="true" aria-labelledby="about-title" aria-describedby="about-desc">
          <div ref={aboutFocusRef} tabIndex={-1} className="about-modal about-full premium-about" data-state={showAbout ? 'open' : 'closed'}>
            {/* Top bar with back button */}
            <div className="about-topbar">
              <button onClick={() => setShowAbout(false)} className="about-back-btn" aria-label="Back to main application">
                <span className="back-icon" aria-hidden>←</span>
                <span>Back</span>
              </button>
            </div>
            {/* Structured Overview */}
            <header className="about-header about-header-wrap">
              <span className="about-logo logo-3d" aria-hidden>
                <span className="logo-core">
                  <svg viewBox="0 0 24 24" fill="currentColor" className="w-8 h-8"><path d="M12 2c4 2 8 6 8 10s-4 8-8 10C8 20 4 16 4 12S8 4 12 2z"/></svg>
                </span>
              </span>
              <div className="about-heading-block">
                <h2 id="about-title" className="about-title">Leaf Vision <span className="about-version">v1.0</span></h2>
                <p id="about-desc" className="about-sub">AI‑powered crop leaf disease detection & contextual agronomy chat</p>
              </div>
            </header>
            <section className="about-overview" aria-label="About Leaf Vision Overview">
              <h3 className="overview-title">About Leaf Vision</h3>
              <div className="overview-grid centered-cards">
                {/* General Description with composite icon (DeepSeek orbit around leaf) */}
                <article className="overview-card premium-tile primary-card">
                  <div className="overview-icon icon-wrap composite-icon" aria-hidden>
                    <div className="orbit">
                      <img src={DeepSeekLogo} alt="" loading="lazy" className="orbit-img" />
                    </div>
                    <div className="center-leaf">
                      <svg viewBox="0 0 24 24" fill="currentColor" className="leaf-svg"><path d="M12 2c4 2 8 6 8 10s-4 8-8 10C8 20 4 16 4 12S8 4 12 2z"/></svg>
                    </div>
                  </div>
                  <h4 className="primary-card-title">General Description</h4>
                  <p className="primary-card-body colorful-text">Leaf Vision is a Vision Transformer (ViT) powered web application for identifying plant leaf diseases in smart agriculture workflows. It delivers real‑time analysis to support improved crop management and yield protection.</p>
                </article>
              </div>
              {/* Stacked centered sub description cards */}
              <div className="sub-cards-row">
                <article className="overview-card premium-tile sub-card">
                  <div className="overview-icon icon-wrap" aria-hidden>
                    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M5 3h14a2 2 0 012 2v11a4 4 0 01-4 4H9l-4 3v-3H5a2 2 0 01-2-2V5a2 2 0 012-2z"/></svg>
                  </div>
                  <h4 className="sub-card-title">Disease Detection</h4>
                  <p className="sub-card-text">Trained on diverse crop imagery (corn, potato, rice & wheat), the model analyzes leaf photos to surface early disease signals and classify health conditions with clear confidence scores.</p>
                </article>
                <article className="overview-card premium-tile sub-card">
                  <div className="overview-icon image icon-wrap deepseek-round" aria-hidden>
                    <img src={DeepSeekLogo} alt="DeepSeek" loading="lazy" />
                    <span className="leaf-overlay-mini">
                      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4"><path d="M12 2c4 2 8 6 8 10s-4 8-8 10C8 20 4 16 4 12S8 4 12 2z"/></svg>
                    </span>
                  </div>
                  <h4 className="sub-card-title">AI Assistant Support</h4>
                  <p className="sub-card-text">DeepSeek integration augments detection with a conversational agronomy assistant that explains symptoms and provides prevention & treatment guidance in farmer‑friendly language.</p>
                </article>
                <article className="overview-card premium-tile sub-card">
                  <div className="overview-icon icon-wrap" aria-hidden>
                    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 22c4.97 0 9-4.03 9-9v-1h-3v1a6 6 0 11-6-6h1V4h-1C7.03 4 3 8.03 3 13s4.03 9 9 9z"/></svg>
                  </div>
                  <h4 className="sub-card-title">Purpose</h4>
                  <ul className="purpose-list sub-card-text">
                    <li>Enable real‑time plant disease detection from images.</li>
                    <li>Provide accessible prevention & treatment advice.</li>
                    <li>Empower smart farming with AI‑driven insight.</li>
                  </ul>
                </article>
              </div>
            </section>
            <footer className="about-foot">Educational use only. Not a substitute for certified agronomic diagnosis.</footer>
          </div>
        </div>
      )}
      <div className="pointer-events-none text-center text-xs text-gray-500 py-3">For educational use. Not a substitute for professional diagnosis.</div>
    </div>
  )
}

export default App
