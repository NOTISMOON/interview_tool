/**
 * 语音识别 Hook（浏览器 Web Speech API，面试流程功能文档 §8）。
 *
 * 能力与约束：
 *   - webkitSpeechRecognition（Chrome/Edge）持续识别，lang=zh-CN；
 *   - interimResults 实时上屏，最终结果累加为 transcript；
 *   - 识别结果允许用户编辑修正后再提交（textarea 受控回填）；
 *   - onerror 分类处理：network / service-not-allowed / language-not-supported
 *     （服务级不可用，停止自动续听避免无限重试循环）、not-allowed（提示开权限）、
 *     no-speech（静默续听）；连续失败可随时改用键盘输入（不降级整场）；
 *   - Edge 已知平台缺陷：Edge Chromium 未完整启用 SpeechRecognition，即使能
 *     new 出对象也常报 network/language-not-supported -> isEdge 供 UI 给出专属提示；
 *   - Firefox 等不支持浏览器：isSupported=false，仅键盘输入；
 *   - Chrome 识别经 Google 云端处理，断网/防火墙可能报 network。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

/** SpeechRecognition 兼容类型声明（标准属性子集） */
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

/** 识别结果事件（标准 SpeechRecognitionEvent 属性子集） */
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
}

type RecognitionCtor = new () => SpeechRecognitionLike;

/** 服务级不可用错误码：识别服务本身挂了/不支持该语言，自动续听只会无限重试失败。
 *  （Edge 未完整启用 SpeechRecognition 时即典型报 network/language-not-supported） */
const SERVICE_FATAL_ERRORS = new Set(['network', 'service-not-allowed', 'language-not-supported', 'audio-capture']);

/** 是否为 Edge（已知 SpeechRecognition 半套实现，报错频繁，UI 据此给出专属提示） */
const isEdgeEnv = () => typeof navigator !== 'undefined' && /Edg\//.test(navigator.userAgent);

/** 获取浏览器 SpeechRecognition 构造器（带 webkit 前缀） */
function getRecognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** hook 对外状态 */
interface UseSpeechRecognition {
  /** 当前浏览器是否支持语音识别 */
  isSupported: boolean;
  /** 是否为 Edge（SpeechRecognition 半套实现，UI 可提示改用 Chrome） */
  isEdge: boolean;
  /** 是否正在识别（录音中） */
  isListening: boolean;
  /** 已确认的累计转写文本（可编辑，编辑后不会被覆盖） */
  transcript: string;
  /** 实时中间结果（灰色预览用） */
  interim: string;
  /** 最近一次错误码（network / not-allowed / aborted 等） */
  error: string | null;
  /** 开始识别 */
  start: () => void;
  /** 停止识别（保留已确认文本） */
  stop: () => void;
  /** 清空转写文本 */
  reset: () => void;
  /** 用户手动编辑转写文本（编辑后停止覆盖） */
  setTranscript: (text: string) => void;
}

/** 连续识别的自动重启间隔（onend 后静默续听） */
const RESTART_DELAY_MS = 400;

export function useSpeechRecognition(): UseSpeechRecognition {
  const [isSupported] = useState<boolean>(() => getRecognitionCtor() !== null);
  const [isEdge] = useState<boolean>(() => isEdgeEnv());
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscriptState] = useState('');
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  /** 用户是否手动停止（手动停止不自动重启） */
  const manualStopRef = useRef(false);
  /** 组件卸载标记 */
  const disposedRef = useRef(false);

  /** 创建/复用识别实例并绑定回调 */
  const ensureRecognition = useCallback((): SpeechRecognitionLike | null => {
    if (recognitionRef.current) return recognitionRef.current;
    const Ctor = getRecognitionCtor();
    if (!Ctor) return null;

    const recognition = new Ctor();
    recognition.lang = 'zh-CN';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      let finalText = '';
      let interimText = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? '';
        if (result.isFinal) {
          finalText += text;
        } else {
          interimText += text;
        }
      }
      if (finalText) {
        // 仅累加新确认段，不覆盖用户已编辑内容
        setTranscriptState((prev) => (prev ? `${prev}${finalText}` : finalText.trimStart()));
      }
      setInterim(interimText);
    };

    recognition.onerror = (event) => {
      const code = event.error;
      // aborted：手动stop触发的正常中止，不算错误
      if (code !== 'aborted') {
        setError(code);
      }
      // not-allowed / service-not-allowed：权限被拒或服务被禁用 → 停止自动续听
      // 服务级不可用（network 等）：Edge 等环境下会无限报错，停止自动续听防止
      // 死循环重试（onend 不再重启，用户可点"继续语音识别"手动恢复）
      if (code === 'not-allowed' || SERVICE_FATAL_ERRORS.has(code)) {
        manualStopRef.current = true;
        setIsListening(false);
      }
      // no-speech：静默周期无输入，onend 会自动续听
    };

    recognition.onend = () => {
      setInterim('');
      // 非手动停止（断续/超时）时自动续听，保持 continuous 体验
      if (!manualStopRef.current && !disposedRef.current) {
        window.setTimeout(() => {
          if (!manualStopRef.current && !disposedRef.current) {
            try {
              recognition.start();
            } catch {
              // start 抛错（如已启动）忽略
            }
          }
        }, RESTART_DELAY_MS);
      } else {
        setIsListening(false);
      }
    };

    recognitionRef.current = recognition;
    return recognition;
  }, []);

  const start = useCallback(() => {
    if (!isSupported) return;
    const recognition = ensureRecognition();
    if (!recognition) return;
    manualStopRef.current = false;
    setError(null);
    try {
      recognition.start();
      setIsListening(true);
    } catch {
      // 已在运行中：忽略
      setIsListening(true);
    }
  }, [ensureRecognition, isSupported]);

  const stop = useCallback(() => {
    manualStopRef.current = true;
    const recognition = recognitionRef.current;
    if (recognition) {
      try {
        recognition.stop();
      } catch {
        // 未运行时 stop 抛错忽略
      }
    }
    setIsListening(false);
    setInterim('');
  }, []);

  const reset = useCallback(() => {
    setTranscriptState('');
    setInterim('');
    setError(null);
  }, []);

  /** 用户编辑入口：同时清掉中间结果避免覆盖 */
  const setTranscript = useCallback((text: string) => {
    setTranscriptState(text);
    setInterim('');
  }, []);

  // 组件卸载：停止识别并释放
  useEffect(() => {
    disposedRef.current = false;
    return () => {
      disposedRef.current = true;
      manualStopRef.current = true;
      const recognition = recognitionRef.current;
      if (recognition) {
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        try {
          recognition.abort();
        } catch {
          // 忽略
        }
        recognitionRef.current = null;
      }
    };
  }, []);

  return { isSupported, isEdge, isListening, transcript, interim, error, start, stop, reset, setTranscript };
}
