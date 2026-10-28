#!/usr/bin/env python3
"""
s15: Integrated Harness - combine the course mechanisms in one runtime.
涓枃锛氱 15 绔犻泦鎴愭鏋垛€斺€斿皢璇剧▼涓殑鍚勯」鏈哄埗缁勫悎鍒颁竴涓繍琛屾椂涓€?
Run:  python s15_integrated_harness/code.py
涓枃锛氳繍琛屽懡浠わ細python s15_integrated_harness/code.py
Need: pip install anthropic python-dotenv pyyaml + .env with ANTHROPIC_API_KEY
涓枃锛氫緷璧?anthropic銆乸ython-dotenv銆乸yyaml锛屽苟鍦?.env 涓厤缃?ANTHROPIC_API_KEY銆?
    scheduled work锛堝畾鏃朵换鍔★級--+            +-- team events锛堝洟闃熶簨浠讹級
                       v                    v
    +---------------------------------------------------+
    | Agent loop锛圓gent 寰幆锛?                         |
    | prompt锛堟彁绀猴級-> model锛堟ā鍨嬶級-> tool calls锛堝伐鍏疯皟鐢級|
    | -> results锛堢粨鏋滐級-> prompt锛堟彁绀猴級               |
    +-------------------------+-------------------------+
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
    built-in tools      persistent teams      MCP tools
    锛堝唴缃伐鍏凤級         锛堟寔涔呭洟闃燂級           锛圡CP 宸ュ叿锛?"""

import ast
import atexit
import fcntl
import importlib.util
import json
import os
import random
import re
import secrets
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
import yaml

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)  # 缁熶竴浠?.env 鍒锋柊閰嶇疆锛岀‘淇濈 15 绔犳暣鍚堢殑鍚勫瓙绯荤粺浣跨敤鍚屼竴濂楄繍琛屽弬鏁般€?if os.getenv("ANTHROPIC_BASE_URL"):  # 浣跨敤鍏煎缃戝叧鏃讹紝閬垮厤瀹樻柟閴存潈鍙橀噺涓庣綉鍏抽壌鏉冩柟寮忓彂鐢熷啿绐併€?    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)  # 鍙Щ闄ゅ彲鑳藉啿绐佺殑浠ょ墝锛屼笉褰卞搷 API Key 绛夊叾浠栭厤缃€?
WORKDIR = Path.cwd()  # 灏嗗惎鍔ㄧ洰褰曚綔涓轰换鍔°€佹妧鑳姐€佽蹇嗗拰宸ュ叿鍏卞悓閬靛畧鐨勫伐浣滃尯杈圭晫銆?client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))  # 鍒涘缓鍏ㄥ眬瀹㈡埛绔紝渚涗富 Agent銆佸瓙 Agent 鍜岃蹇嗘ā鍧楀鐢ㄣ€?MODEL = os.environ["MODEL_ID"]  # 涓绘ā鍨嬫槸蹇呭～閰嶇疆锛涚己澶辨椂绔嬪嵆澶辫触锛岄伩鍏嶈繍琛屼腑閫旀墠鏆撮湶閿欒銆?PRIMARY_MODEL = MODEL  # 淇濆瓨棣栭€夋ā鍨嬶紝渚夸簬閿欒鎭㈠鍚庝粠闄嶇骇妯″瀷鍒囧洖銆?FALLBACK_MODEL = os.getenv("FALLBACK_MODEL_ID")  # 闄嶇骇妯″瀷鍙€夛紝浠呭湪杩炵画鏈嶅姟閿欒鏃跺惎鐢ㄣ€?
SKILLS_DIR = WORKDIR / "skills"  # 绗?7 绔犵殑鎶€鑳芥満鍒跺湪鏁村悎鐗堜腑缁熶竴浠庡伐浣滃尯 skills 鐩綍鍙戠幇銆?TRANSCRIPT_DIR = WORKDIR / ".transcripts"  # 鍘嬬缉涓婁笅鏂囧墠鍏堜繚瀛樺畬鏁翠細璇濓紝閬垮厤鎽樿閫犳垚鍘嗗彶淇℃伅涓嶅彲鎭㈠銆?TOOL_RESULTS_DIR = WORKDIR / ".task_outputs" / "tool-results"  # 澶у瀷宸ュ叿杈撳嚭钀界洏鍚庯紝娑堟伅鍘嗗彶鍙繚鐣欒矾寰勫拰棰勮銆?
DEFAULT_MAX_TOKENS = 8000  # 姝ｅ父杞閲囩敤杈冨皬杈撳嚭棰勭畻锛屾帶鍒跺欢杩熷拰鎴愭湰銆?ESCALATED_MAX_TOKENS = 16000  # 棣栨琚?max_tokens 鎴柇鍚庢墿澶ч绠楋紝浼樺厛璁╁綋鍓嶅伐浣滆嚜鐒跺畬鎴愩€?MAX_RETRIES = 3  # 闄愬埗鏅€氱灛鏃堕敊璇殑閲嶈瘯娆℃暟锛岄槻姝?Agent 鏃犻檺闃诲銆?MAX_CONSECUTIVE_529 = 2  # 杩炵画鍑虹幇鏈嶅姟杩囪浇鍚庤Е鍙戞ā鍨嬮檷绾э紝鑰屼笉鏄寔缁姹傚悓涓€妯″瀷銆?MAX_RECOVERY_RETRIES = 2  # 杈撳嚭宸叉墿瀹逛粛琚埅鏂椂锛屾渶澶氳拷鍔犱袱娆＄户缁彁绀恒€?BASE_DELAY_MS = 500  # 鎸囨暟閫€閬跨殑鍩虹闂撮殧锛屽悗缁噸璇曚細鍦ㄦ鍩虹涓婂闀垮苟鍔犲叆鎶栧姩銆?CONTEXT_LIMIT = 50000  # 鍙戦€佹ā鍨嬪墠鐨勮蒋瀛楃涓婇檺锛岀敤浜庢彁鍓嶅惎鍔ㄥ垎灞傚帇缂┿€?KEEP_RECENT_TOOL_RESULTS = 3  # 濮嬬粓淇濈暀鏈€杩戝伐鍏风粨鏋滐紝纭繚妯″瀷鑳界湅鍒板綋鍓嶆搷浣滅殑鐩存帴鍙嶉銆?PERSIST_THRESHOLD = 30000  # 瓒呰繃璇ラ暱搴︾殑鍗曚釜宸ュ叿缁撴灉鍐欏叆纾佺洏锛岄伩鍏嶆尋鍗犲璇濅笂涓嬫枃銆?CONTINUATION_PROMPT = "璇蜂粠涓婁竴鏉″搷搴斾腑鏂缁х画锛屼笉瑕侀噸澶嶅凡缁忓畬鎴愮殑宸ヤ綔銆?  # 鎴柇鎭㈠鏃惰姹傜画鍐欎笖涓嶉噸鍋氬凡瀹屾垚姝ラ銆?PROMPT = "\033[36ms15 >> \033[0m"  # 鏅€氱粓绔娇鐢ㄧ殑褰╄壊浜や簰鎻愮ず绗︺€?# \001/\002 tell Readline the ANSI escapes have zero display width.锝滀腑鏂囷細鍛婄煡 Readline锛孉NSI 杞箟搴忓垪涓嶅崰鏄剧ず瀹藉害銆?READLINE_PROMPT = "\001\033[36m\002s15 >> \001\033[0m\002"  # Readline 鐗堟湰棰濆鏍囪涓嶅彲瑙佸瓧绗︼紝淇濊瘉鍏夋爣浣嶇疆姝ｇ‘銆?CLI_ACTIVE = False  # 瀵煎叆妯″潡鏃朵繚鎸佸叧闂紝鍙湁鑴氭湰鐩存帴杩愯鍚庢墠鍚敤浜や簰寮忛噸缁樸€?

def load_memory_runtime():  # 鍔犺浇骞舵帴鍏ョ 09 绔犵殑闀挎湡璁板繂杩愯鏃讹紱鏈€鏃╋細15.80
    """Load s09 once and share this host's client, model, and workspace.锝滀腑鏂囷細鍔犺浇涓€娆＄ 09 绔犺繍琛屾椂锛屽苟鍏变韩褰撳墠瀹㈡埛绔€佹ā鍨嬪拰宸ヤ綔鍖恒€?""
    path = Path(__file__).resolve().parents[1] / "s09_memory" / "code.py"  # 瀹氫綅绗?09 绔犲疄鐜帮紝閬垮厤鍦ㄧ 15 绔犲鍒舵暣濂楄蹇嗕唬鐮併€?    spec = importlib.util.spec_from_file_location(  # 涓鸿婧愮爜鍒涘缓鐙珛瀵煎叆鎻忚堪锛岄槻姝笌鏅€氭ā鍧楀悕鍐茬獊銆?        f"integrated_memory_{id(client)}", path  # 鍚嶇О缁戝畾瀹㈡埛绔疄渚嬶紝浣垮悓杩涚▼鍐呬笉鍚屽涓诲郊姝ら殧绂汇€?    )
    if spec is None or spec.loader is None:  # 瀵煎叆鍣ㄦ棤娉曟瀯閫犳椂绔嬪嵆涓锛岄伩鍏嶈繑鍥炲崐鍒濆鍖栫殑璁板繂杩愯鏃躲€?        raise RuntimeError(f"Unable to load memory runtime from {path}")  # 閿欒涓繚鐣欏疄闄呰矾寰勶紝渚夸簬瀹氫綅璇剧▼鐩綍闂銆?    runtime = importlib.util.module_from_spec(spec)  # 鍏堝垱寤烘ā鍧楀璞★紝灏氫笉鎵ц绗?09 绔犵殑椤跺眰浠ｇ爜銆?    spec.loader.exec_module(runtime)  # 鏄惧紡鎵ц妯″潡锛屼娇鍏朵腑鐨勮蹇嗗嚱鏁板拰甯搁噺鍙緵鏁村悎灞傝皟鐢ㄣ€?    runtime.WORKDIR = WORKDIR  # 瑕嗙洊绗?09 绔犺嚜宸辩殑鍚姩鐩綍锛屼娇璁板繂涓庣 15 绔犲叡浜伐浣滃尯銆?    runtime.MEMORY_DIR = WORKDIR / ".memory"  # 鎶婇暱鏈熻蹇嗗浐瀹氬埌鏁村悎椤圭洰鐨勯殣钘忕洰褰曘€?    runtime.MEMORY_INDEX = runtime.MEMORY_DIR / "MEMORY.md"  # 鍚屾淇绱㈠紩璺緞锛岄伩鍏嶄粛鎸囧悜鏃х珷鑺傜洰褰曘€?    runtime.client = client  # 娉ㄥ叆缁熶竴瀹㈡埛绔紝閬垮厤璁板繂妯″潡鍙﹀缓杩炴帴鍜岃鍙栧彟涓€濂楅厤缃€?    runtime.MODEL = MODEL  # 璁板繂鎻愬彇涓庝富寰幆浣跨敤鍚屼竴妯″瀷锛屼繚鎸佸搷搴旇兘鍔涗竴鑷淬€?    return runtime  # 杩斿洖宸查噸缁戝畾瀹夸富璧勬簮鐨勭 09 绔犳ā鍧楀璞°€?

MEMORY_RUNTIME = load_memory_runtime()  # 鍚姩鏃跺彧鍔犺浇涓€娆★紝鍚庣画姣忚疆鐩存帴澶嶇敤鍏朵腑鐨勫彫鍥炰笌鏁寸悊鑳藉姏銆?

class ConsoleBroker:
    """Serialize normal prompts and worker permission questions on one stdin.锝滀腑鏂囷細鍦ㄥ悓涓€鏍囧噯杈撳叆涓覆琛屽鐞嗘櫘閫氭彁绀哄拰宸ヤ綔绾跨▼鐨勬潈闄愯闂€?""

    def __init__(self):  # 鍒濆鍖?ConsoleBroker 鐨勮繍琛岀姸鎬侊紱鏈€鏃╋細15.104
        self._lock = threading.Lock()  # 鏍囧噯杈撳叆鏄崟涓€璧勬簮锛岀敤閿侀伩鍏嶄富绾跨▼鍜岄槦鍙嬬嚎绋嬪悓鏃惰鍙栥€?        self.reader = None  # 棰勭暀鍙浛鎹㈣鍙栧櫒锛屼究浜庢祴璇曟椂娉ㄥ叆杈撳叆鍑芥暟鑰屼笉渚濊禆鐪熷疄缁堢銆?        self.display_prompt = PROMPT  # 鍚庡彴杈撳嚭瀹屾垚鍚庣敤鏅€氭彁绀虹鎭㈠鐢ㄦ埛鐪嬪埌鐨勮緭鍏ヨ銆?        self.readline_prompt = READLINE_PROMPT  # 涓讳氦浜掕鍙栦娇鐢?Readline 瀹夊叏鐗堟湰锛岄槻姝?ANSI 鐮村潖鍏夋爣璁＄畻銆?
    def set_prompt(self, display_prompt: str, readline_prompt: str):  # 鏇存柊缁堢鏄剧ず鎻愮ず绗﹀拰 Readline 鎻愮ず绗︼紱鏈€鏃╋細15.110
        self.display_prompt = display_prompt  # 鍚屾鏇存柊閲嶇粯鏃舵樉绀虹殑鎻愮ず绗︺€?        self.readline_prompt = readline_prompt  # 鍚屾鏇存柊闃诲璇诲彇鏃朵娇鐢ㄧ殑鎻愮ず绗︺€?
    def ask(self, prompt: str | None = None) -> str:  # 涓茶璇诲彇鐢ㄦ埛鎴栨潈闄愮‘璁よ緭鍏ワ紱鏈€鏃╋細15.114
        with self._lock:  # 鏁翠釜 input 璋冪敤鏈熼棿鎸侀攣锛屼繚璇佹潈闄愯闂笉浼氭彃鍏ユ櫘閫氶棶棰樿緭鍏ヤ腑銆?            active_prompt = self.readline_prompt if prompt is None else prompt  # 鏃犳樉寮忔彁绀烘椂浣跨敤涓?CLI 鎻愮ず绗︼紝鍚﹀垯鏄剧ず鏉冮檺闂銆?            return (self.reader or input)(active_prompt)  # 浼樺厛浣跨敤娴嬭瘯璇诲彇鍣紝鐢熶骇鐜鍥為€€鍒板唴缃?input銆?

CONSOLE = ConsoleBroker()  # 鍏ㄩ儴绾跨▼鍏变韩鍚屼竴杈撳叆鍗忚皟鍣紝褰㈡垚鍞竴鐨勭粓绔叆鍙ｃ€?

def terminal_print(text: str):  # 鍦ㄧ嚎绋嬪畨鍏ㄧ殑缁堢涓緭鍑烘秷鎭紱鏈€鏃╋細15.123  鈭?    if threading.current_thread() is threading.main_thread() or not CLI_ACTIVE:  # 涓荤嚎绋嬫垨闈炰氦浜掓ā寮忔棤闇€淇濇姢姝ｅ湪缂栬緫鐨勮緭鍏ヨ銆?        print(text)  # 鐩存帴杈撳嚭鍙伩鍏嶅湪鏅€氳剼鏈拰娴嬭瘯鐜寮曞叆缁堢鎺у埗搴忓垪銆?        return  # 缁撴潫绠€鍗曡矾寰勶紝涓嬮潰浠呭鐞嗗悗鍙扮嚎绋嬬殑寮傛杈撳嚭銆?    line = ""  # 榛樿璁や负娌℃湁寰呮仮澶嶈緭鍏ワ紝浠ュ吋瀹逛笉鏀寔 Readline 鐨勫钩鍙般€?    if READLINE_AVAILABLE:  # 鍙湁 Readline 鍙敤鏃舵墠鑳借鍙栫敤鎴峰皻鏈彁浜ょ殑缂撳啿鍖恒€?        try:  # 鏌愪簺闈炵湡瀹炵粓绔櫧鍙鍏?Readline锛屼絾璇诲彇缂撳啿鍖轰粛鍙兘澶辫触銆?            line = readline.get_line_buffer()  # 淇濆瓨鐢ㄦ埛褰撳墠宸茶緭鍏ュ唴瀹癸紝閬垮厤鍚庡彴娑堟伅灏嗗叾瑕嗙洊銆?        except Exception:  # 缁堢閲嶇粯灞炰簬杈呭姪鑳藉姏锛屽け璐ヤ笉搴斾腑鏂?Agent 涓绘祦绋嬨€?            line = ""  # 闄嶇骇涓虹┖缂撳啿鍖猴紝鑷冲皯淇濊瘉鍚庡彴娑堟伅鍙互鏄剧ず銆?    print(f"\r\033[K{text}")  # 鍥炲埌琛岄骞舵竻闄ゅ綋鍓嶈緭鍏ヨ锛屽啀瀹屾暣杈撳嚭鍚庡彴娑堟伅銆?    print(CONSOLE.display_prompt + line, end="", flush=True)  # 鎭㈠鎻愮ず绗﹀拰鏈彁浜ゆ枃鏈紝璁╃敤鎴风户缁師杈撳叆銆?
# -- Task System --锝滀换鍔＄郴缁燂細缁ф壙绗?10 绔犵殑鎸佷箙鍖栦换鍔★紝骞跺惛鏀剁 13 绔犵殑璐熻矗浜恒€佷緷璧栧拰骞跺彂瀹夊叏璁捐銆?
# Tasks are tiny durable records. Later systems add ownership, dependencies,锝滀腑鏂囷細浠诲姟鏄交閲忋€佹寔涔呯殑璁板綍锛涘悗缁郴缁熷湪姝ゅ熀纭€涓婂鍔犺礋璐ｄ汉鍜屼緷璧栵紝
# worktrees, and teammates on top of this same file-backed state.锝滀腑鏂囷細骞剁户缁彔鍔犲伐浣滄爲涓庨槦鍙嬭兘鍔涳紝鍏变韩鍚屼竴濂楁枃浠剁姸鎬併€?TASKS_DIR = WORKDIR / ".tasks"  # 浠诲姟浠ユ枃浠跺舰寮忎繚瀛樺湪宸ヤ綔鍖恒€?TASKS_ROOT = TASKS_DIR.resolve()  # 缂撳瓨浠诲姟鐩綍鐨勮鑼冨寲璺緞銆?TASK_ID_PATTERN = re.compile(r"^task_[0-9a-f]{8}$")  # 闄愬埗浠诲姟 ID 鐨勬牸寮忋€?task_lock = threading.RLock()  # 淇濇姢鍚屼竴杩涚▼鍐呯殑浠诲姟鎿嶄綔銆?TASK_LOCK_PATH = TASKS_DIR / ".lock"  # 璺ㄨ繘绋嬮攣浣跨敤鐨勬枃浠躲€?_task_store_state = threading.local()  # 涓烘瘡涓嚎绋嬩繚瀛橀攣鐨勫祵濂楃姸鎬併€?CURRENT_TODOS: list[dict] = []  # 淇濆瓨褰撳墠寰呭姙鍒楄〃銆?
# owner -> {"task_id": str, "cwd": Path}. A teammate gets one assignment at锝滀腑鏂囷細璇ヨ〃璁板綍璐熻矗浜哄搴旂殑浠诲姟鍜岀洰褰曪紱姣忓悕闃熷弸鍚屾椂鍙帴涓€涓换鍔★紝
# a time, and every filesystem tool resolves its cwd through this registry.锝滀腑鏂囷細鎵€鏈夋枃浠跺伐鍏烽兘閫氳繃姝ゆ敞鍐岃〃瑙ｆ瀽褰撳墠宸ヤ綔鐩綍銆?teammate_assignments: dict[str, dict[str, object]] = {}  # 璁板綍璐熻矗浜轰笌浠诲姟宸ヤ綔鐩綍鐨勭粦瀹氥€?assignment_versions: dict[str, int] = {}  # 璁板綍鍚勮礋璐ｄ汉鐨勫垎閰嶇増鏈€?

@contextmanager  # 灏嗙敓鎴愬櫒鍑芥暟杞崲涓轰笂涓嬫枃绠＄悊鍣ㄣ€?def task_store_lock():  # 璺ㄧ嚎绋嬨€佽法杩涚▼閿佸畾浠诲姟瀛樺偍锛涙渶鏃╋細13.72
    """Serialize task mutations across threads and host processes.锝滀腑鏂囷細璺ㄧ嚎绋嬪強瀹夸富杩涚▼涓茶鎵ц浠诲姟鍙樻洿銆?""
    with task_lock:  # 鍏堣幏鍙栬繘绋嬪唴鍙噸鍏ラ攣銆?        depth = getattr(_task_store_state, "depth", 0)  # 璇诲彇褰撳墠绾跨▼鐨勫祵濂楁繁搴︺€?        if depth == 0:  # 鏈€澶栧眰璋冪敤鎵嶈幏鍙栨枃浠堕攣銆?            TASKS_DIR.mkdir(parents=True, exist_ok=True)  # 纭繚浠诲姟鐩綍瀛樺湪銆?            handle = TASK_LOCK_PATH.open("a+", encoding="utf-8")  # 鎵撳紑閿佹枃浠躲€?            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)  # 鑾峰彇璺ㄨ繘绋嬫帓浠栭攣銆?            _task_store_state.handle = handle  # 鍦ㄧ嚎绋嬫湰鍦颁繚瀛樻枃浠跺彞鏌勩€?        _task_store_state.depth = depth + 1  # 澧炲姞宓屽娣卞害銆?        try:  # 纭繚閫€鍑烘椂閲婃斁閿併€?            yield  # 灏嗘帶鍒舵潈浜ょ粰涓婁笅鏂囦腑鐨勬搷浣溿€?        finally:  # 鏃犺鎿嶄綔鏄惁鍑洪敊閮芥墽琛屾竻鐞嗐€?            _task_store_state.depth -= 1  # 鍑忓皯宓屽娣卞害銆?            if _task_store_state.depth == 0:  # 鏈€澶栧眰閫€鍑烘椂閲婃斁鏂囦欢閿併€?                handle = _task_store_state.handle  # 鍙栧嚭姝ゅ墠淇濆瓨鐨勫彞鏌勩€?                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # 瑙ｉ櫎鏂囦欢閿併€?                handle.close()  # 鍏抽棴閿佹枃浠躲€?                del _task_store_state.handle  # 娓呴櫎绾跨▼鏈湴鍙ユ焺銆?

def advance_assignment_version(owner: str):  # 鏇存柊浠诲姟鍒嗛厤鐗堟湰骞朵娇鏃ц鍒掑鎵瑰け鏁堬紱鏈€鏃╋細13.93 鈭?    """Invalidate old approvals without clearing an explicit plan requirement.锝滀腑鏂囷細浣挎棫瀹℃壒澶辨晥锛屼絾淇濈暀鏄庣‘鐨勮鍒掕姹傘€?""
    with task_lock:  # 鎸侀攣鏇存柊鍒嗛厤鐗堟湰銆?        assignment_versions[owner] = assignment_versions.get(owner, 0) + 1  # 鐗堟湰閫掑浠ュ尯鍒嗘柊鏃у垎閰嶃€?        gates = globals().get("plan_gates")  # 鑾峰彇鍙兘灏氭湭鍒濆鍖栫殑璁″垝闂ㄦ帶銆?        request_ids = globals().get("plan_request_ids")  # 鑾峰彇璁″垝璇锋眰缂栧彿琛ㄣ€?        team = globals().get("team_lock")  # 鑾峰彇鍥㈤槦鐘舵€侀攣銆?        if team is not None:  # 鍥㈤槦閿佸凡鍒濆鍖栨椂銆?            team.acquire()  # 鑾峰彇鍥㈤槦閿併€?        try:  # 纭繚鏈€缁堥噴鏀惧洟闃熼攣銆?            if (isinstance(gates, dict) and owner in gates  # 妫€鏌ヨ礋璐ｄ汉鏄惁鏈夎鍒掗棬鎺с€?                    and gates[owner] != "not_required"):  # 浠呬繚鐣欐槑纭姹傝鍒掔殑闂ㄦ帶銆?                gates[owner] = "required"  # 浣挎棫瀹℃壒澶辨晥骞堕噸鏂拌姹傝鍒掋€?            if isinstance(request_ids, dict):  # 璇锋眰缂栧彿琛ㄥ瓨鍦ㄦ椂銆?                request_ids.pop(owner, None)  # 绉婚櫎鏃ц鍒掕姹傜紪鍙枫€?        finally:  # 鏃犺鏄惁鍑洪敊閮芥墽琛屾竻鐞嗐€?            if team is not None:  # 鍥㈤槦閿佸瓨鍦ㄦ椂銆?                team.release()  # 閲婃斁鍥㈤槦閿併€?

@dataclass  # 鑷姩鐢熸垚浠诲姟鏁版嵁绫绘柟娉曘€?class Task:  # 琛ㄧず涓€涓寔涔呭寲浠诲姟銆?    id: str  # 浠诲姟鍞竴缂栧彿銆?    subject: str  # 浠诲姟涓婚銆?    description: str  # 浠诲姟璇︾粏鎻忚堪銆?    status: str  # 浠诲姟褰撳墠鐘舵€併€?    owner: str | None  # 浠诲姟璐熻矗浜猴紝鍙负绌恒€?    blockedBy: list[str]  # 蹇呴』鍏堝畬鎴愮殑浠诲姟 ID 鍒楄〃銆?    worktree: str | None = None  # 缁戝畾鐨勫伐浣滄爲鍚嶇О锛屽彲涓虹┖銆?

def _task_path(task_id: str) -> Path:  # 鐢熸垚骞舵牎楠屼换鍔?JSON 鏂囦欢璺緞锛涙渶鏃╋細13.124 鈭?    if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):  # 浠诲姟 ID 蹇呴』绗﹀悎鍥哄畾鏍煎紡銆?        raise ValueError(f"Invalid task ID: {task_id!r}")  # 鎷掔粷鏃犳晥浠诲姟缂栧彿銆?    path = (TASKS_DIR / f"{task_id}.json").resolve()  # 瑙ｆ瀽浠诲姟 JSON 璺緞銆?    if (not TASKS_ROOT.is_relative_to(WORKDIR.resolve())  # 纭繚浠诲姟鏍圭洰褰曚綅浜庡伐浣滃尯鍐呫€?            or not path.is_relative_to(TASKS_ROOT)):  # 纭繚浠诲姟鏂囦欢浣嶄簬浠诲姟鏍圭洰褰曞唴銆?        raise ValueError(f"Invalid task ID: {task_id!r}")  # 鎷掔粷瓒婄晫璺緞銆?    return path  # 杩斿洖瀹夊叏浠诲姟璺緞銆?

def create_task(subject: str, description: str = "") -> Task:  # 鍒涘缓骞舵寔涔呭寲鏂颁换鍔★紱鏈€鏃╋細10.199 鈭?    subject = subject.strip()  # 鍘婚櫎涓婚涓ょ绌虹櫧銆?    if not subject:  # 涓婚涓嶈兘涓虹┖銆?        raise ValueError("Task subject cannot be empty")  # 鎷掔粷绌轰富棰樸€?    with task_store_lock():  # 鎸侀攣鍒涘缓浠诲姟鏂囦欢銆?        for _ in range(100):  # 闄愬畾鐢熸垚鍞竴缂栧彿鐨勫皾璇曟鏁般€?            task = Task(  # 鏋勯€犳柊浠诲姟銆?                id=f"task_{secrets.token_hex(4)}",  # 鐢熸垚闅忔満鍗佸叚杩涘埗浠诲姟 ID銆?                subject=subject,  # 璁剧疆浠诲姟涓婚銆?                description=description,  # 璁剧疆璇︾粏鎻忚堪銆?                status="pending",  # 鍒濆鐘舵€佷负寰呭鐞嗐€?                owner=None,  # 鍒濆鏃犺礋璐ｄ汉銆?                blockedBy=[],  # 鍒濆鏃犱緷璧栥€?            )  # 缁撴潫浠诲姟瀵硅薄鏋勯€犮€?            try:  # 灏濊瘯鐙崰鍒涘缓浠诲姟鏂囦欢銆?                with _task_path(task.id).open("x", encoding="utf-8") as handle:  # x 妯″紡閬垮厤瑕嗙洊宸叉湁浠诲姟銆?                    json.dump(asdict(task), handle, indent=2)  # 灏嗕换鍔″簭鍒楀寲涓?JSON銆?                return task  # 鍒涘缓鎴愬姛鍚庤繑鍥炰换鍔°€?            except FileExistsError:  # 闅忔満 ID 鍐茬獊鏃躲€?                continue  # 閲嶆柊鐢熸垚浠诲姟 ID銆?    raise RuntimeError("Could not allocate a unique task ID")  # 澶氭鍐茬獊鍚庢姤鍛婂け璐ャ€?

def _task_depends_on(task_id: str, target_id: str) -> bool:  # 閫掑綊鍒ゆ柇浠诲姟渚濊禆鍏崇郴锛涙渶鏃╋細13.157  鈭?    """Return whether task_id transitively depends on target_id.锝滀腑鏂囷細鍒ゆ柇 task_id 鏄惁浼犻€掍緷璧?target_id銆?""
    pending = [task_id]  # 浠庤捣濮嬩换鍔″紑濮嬮亶鍘嗕緷璧栧浘銆?    visited = set()  # 璁板綍宸茶闂换鍔′互閬垮厤閲嶅閬嶅巻銆?    while pending:  # 鍙杩樻湁寰呮鏌ヤ换鍔″氨缁х画銆?        current = pending.pop()  # 鍙栧嚭涓€涓緟妫€鏌ヤ换鍔°€?        if current == target_id:  # 鍒拌揪鐩爣浠诲姟琛ㄧず瀛樺湪渚濊禆璺緞銆?            return True  # 杩斿洖瀛樺湪渚濊禆銆?        if current in visited:  # 宸茶闂妭鐐规棤闇€閲嶅澶勭悊銆?            continue  # 璺宠繃璇ヨ妭鐐广€?        visited.add(current)  # 鏍囪鑺傜偣宸茶闂€?        pending.extend(load_task(current).blockedBy)  # 灏嗗叾鍓嶇疆浠诲姟鍔犲叆寰呮鏌ュ垪琛ㄣ€?    return False  # 閬嶅巻缁撴潫浠嶆湭鍒拌揪鐩爣銆?

def update_task(task_id: str, addBlockedBy: list[str]) -> Task:  # 鏇存柊浠诲姟鐨勪緷璧栧叧绯伙紱鏈€鏃╋細10.203  鈭?    """Add dependency edges after create_task has returned real task IDs.锝滀腑鏂囷細鍦?create_task 杩斿洖鐪熷疄浠诲姟 ID 鍚庢坊鍔犱緷璧栬竟銆?""
    if not isinstance(addBlockedBy, list):  # 渚濊禆鍙傛暟蹇呴』鏄垪琛ㄣ€?        raise ValueError("addBlockedBy must be a list of task IDs")  # 鎷掔粷鏃犳晥鍙傛暟绫诲瀷銆?
    with task_store_lock():  # 鎸侀攣妫€鏌ュ苟鏇存柊渚濊禆銆?        task = load_task(task_id)  # 璇诲彇鐩爣浠诲姟銆?        if task.status != "pending" or task.owner is not None:  # 鍙湁鏈鍙栫殑寰呭鐞嗕换鍔″彲淇敼渚濊禆銆?            raise ValueError(  # 鐘舵€佷笉绗﹀悎鏃舵姤鍛婇敊璇€?                f"Task {task_id} dependencies can only be updated while "  # 璇存槑鍙兘鍦ㄥ緟澶勭悊鐘舵€佷笅淇敼銆?                "pending and unowned"  # 璇存槑浠诲姟杩樺繀椤绘湭鍒嗛厤銆?            )  # 缁撴潫寮傚父鏋勯€犮€?
        dependencies = list(dict.fromkeys(addBlockedBy))  # 鍘婚噸骞朵繚鐣欒緭鍏ラ『搴忋€?        for dependency in dependencies:  # 閫愪釜楠岃瘉鏂板渚濊禆銆?            if dependency == task_id:  # 浠诲姟涓嶈兘渚濊禆鑷韩銆?                raise ValueError("Task cannot depend on itself")  # 鎷掔粷鑷緷璧栥€?            if not _task_path(dependency).is_file():  # 妫€鏌ヤ緷璧栦换鍔℃枃浠舵槸鍚﹀瓨鍦ㄣ€?                raise ValueError(f"Dependency not found: {dependency}")  # 鎷掔粷涓嶅瓨鍦ㄧ殑渚濊禆銆?            if dependency not in task.blockedBy and _task_depends_on(  # 鏂板渚濊禆鍓嶆鏌ユ槸鍚﹀舰鎴愮幆銆?                dependency, task_id  # 妫€鏌ュ墠缃换鍔℃槸鍚﹀弽鍚戜緷璧栧綋鍓嶄换鍔°€?            ):  # 缁撴潫鐜鏌ャ€?                raise ValueError(  # 鍙戠幇渚濊禆鐜椂鎷掔粷鏇存柊銆?                    f"Dependency cycle detected: {task_id} -> {dependency}"  # 鎶ュ憡褰㈡垚鐜殑杈广€?                )  # 缁撴潫寮傚父鏋勯€犮€?
        task.blockedBy.extend(  # 杩藉姞閫氳繃鏍￠獙鐨勪緷璧栥€?            dependency for dependency in dependencies  # 閫愪釜澶勭悊宸插幓閲嶇殑渚濊禆銆?            if dependency not in task.blockedBy  # 璺宠繃宸插瓨鍦ㄧ殑渚濊禆銆?        )  # 瀹屾垚渚濊禆鍒楄〃鏇存柊銆?        save_task(task)  # 鎸佷箙鍖栨洿鏂板悗鐨勪换鍔°€?        return task  # 杩斿洖鏇存柊鍚庣殑浠诲姟銆?

def save_task(task: Task):  # 鍘熷瓙鍐欏叆浠诲姟鐘舵€佹枃浠讹紱鏈€鏃╋細13.206  鈭?    with task_store_lock():  # 鎸侀攣淇濆瓨浠诲姟銆?        path = _task_path(task.id)  # 楠岃瘉浠诲姟 ID 骞跺畾浣嶆枃浠躲€?        temporary = path.with_name(  # 涓烘湰娆″啓鍏ユ瀯閫犱复鏃舵枃浠跺悕銆?            f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"  # 浣跨敤杩涚▼鍜岀嚎绋?ID 閬垮厤鍐茬獊銆?        )  # 瀹屾垚涓存椂璺緞鏋勯€犮€?        try:  # 纭繚寮傚父鏃朵篃娓呯悊涓存椂鏂囦欢銆?            temporary.write_text(  # 鍏堝啓鍏ヤ复鏃舵枃浠躲€?                json.dumps(asdict(task), indent=2), encoding="utf-8"  # 搴忓垪鍖栦换鍔″苟浣跨敤 UTF-8 缂栫爜銆?            )  # 缁撴潫鏂囦欢鍐欏叆銆?            os.replace(temporary, path)  # 鍘熷瓙鏇挎崲鐩爣浠诲姟鏂囦欢銆?        finally:  # 鏃犺鎴愬姛涓庡惁閮芥墽琛屾竻鐞嗐€?            temporary.unlink(missing_ok=True)  # 鍒犻櫎鍙兘娈嬬暀鐨勪复鏃舵枃浠躲€?

def load_task(task_id: str) -> Task:  # 璇诲彇骞惰В鏋愭寚瀹氫换鍔★紱鏈€鏃╋細10.207  鈭?    with task_lock:  # 鎸佽繘绋嬪唴閿佽鍙栦换鍔°€?        data = json.loads(_task_path(task_id).read_text(encoding="utf-8"))  # 璇诲彇骞惰В鏋愪换鍔?JSON銆?        task = Task(**data)  # 灏嗗瓧鍏歌繕鍘熶负浠诲姟瀵硅薄銆?        if task.id != task_id:  # 妫€鏌ユ枃浠跺唴瀹逛笌璇锋眰鐨?ID 鏄惁涓€鑷淬€?            raise ValueError(f"Task file ID does not match {task_id}")  # 涓嶄竴鑷存椂鎷掔粷璇ヨ褰曘€?        if task.status not in {"pending", "in_progress", "completed"}:  # 妫€鏌ヤ换鍔＄姸鎬佹槸鍚﹀彈鏀寔銆?            raise ValueError(f"Invalid task status: {task.status}")  # 鎷掔粷鏃犳晥鐘舵€併€?        return task  # 杩斿洖宸查獙璇佺殑浠诲姟銆?

def list_tasks() -> list[Task]:  # 璇诲彇骞舵帓搴忓叏閮ㄦ寔涔呭寲浠诲姟锛涙渶鏃╋細10.211 鈭?    with task_lock:  # 鎸佽繘绋嬪唴閿佽鍙栦换鍔″垪琛ㄣ€?        if not TASKS_DIR.exists():  # 浠诲姟鐩綍涓嶅瓨鍦ㄦ椂銆?            return []  # 杩斿洖绌哄垪琛ㄣ€?        if not TASKS_ROOT.is_relative_to(WORKDIR.resolve()):  # 妫€鏌ヤ换鍔＄洰褰曟槸鍚︿綅浜庡伐浣滃尯鍐呫€?            raise ValueError("Tasks directory escapes workspace")  # 鐩綍瓒婄晫鏃舵嫆缁濊鍙栥€?        return [load_task(path.stem)  # 鍔犺浇鍖归厤鐨勪换鍔℃枃浠躲€?                for path in sorted(TASKS_DIR.glob("task_*.json"))]  # 鎸夎矾寰勬帓搴忓悗閫愪釜璇诲彇銆?

def get_task_json(task_id: str) -> str:  # 灏嗘寚瀹氫换鍔″簭鍒楀寲涓?JSON锛涙渶鏃╋細15.325
    return json.dumps(asdict(load_task(task_id)), indent=2)  # 灏嗕换鍔″璞¤浆鎹负鏍煎紡鍖?JSON銆?

def can_start(task_id: str) -> bool:  # 鍒ゆ柇浠诲姟渚濊禆鏄惁鍏ㄩ儴瀹屾垚锛涙渶鏃╋細10.230 鈭?    # Dependencies are intentionally simple: every blocker must exist and be锝滀腑鏂囷細渚濊禆瑙勫垯鍒绘剰淇濇寔绠€鍗曪細姣忎釜鍓嶇疆浠诲姟閮藉繀椤诲瓨鍦紝
    # completed before the task can be claimed.锝滀腑鏂囷細骞朵笖鍏ㄩ儴瀹屾垚鍚庢墠鑳借棰嗗綋鍓嶄换鍔°€?    task = load_task(task_id)  # 璇诲彇鐩爣浠诲姟銆?    for dep_id in task.blockedBy:  # 閫愪釜妫€鏌ュ墠缃换鍔°€?        try:  # 楠岃瘉渚濊禆浠诲姟璺緞銆?            dep_path = _task_path(dep_id)  # 瑙ｆ瀽渚濊禆瀵瑰簲鐨勬枃浠惰矾寰勩€?        except ValueError:  # 渚濊禆 ID 鏃犳晥鏃躲€?            return False  # 瑙嗕负涓嶅彲寮€濮嬨€?        if not dep_path.exists():  # 渚濊禆鏂囦欢缂哄け鏃躲€?            return False  # 瑙嗕负涓嶅彲寮€濮嬨€?        if load_task(dep_id).status != "completed":  # 渚濊禆灏氭湭瀹屾垚鏃躲€?            return False  # 瑙嗕负涓嶅彲寮€濮嬨€?    return True  # 鍏ㄩ儴渚濊禆瀹屾垚鍚庡厑璁稿紑濮嬨€?

def _owner_in_progress(owner: str) -> Task | None:  # 鏌ユ壘璐熻矗浜烘鍦ㄦ墽琛岀殑浠诲姟锛涙渶鏃╋細13.263 鈭?    return next((task for task in list_tasks()  # 鏌ユ壘璐熻矗浜烘鍦ㄦ墽琛岀殑浠诲姟銆?                 if task.status == "in_progress" and task.owner == owner), None)  # 鏈壘鍒版椂杩斿洖 None銆?

def _incomplete_dependencies(task: Task) -> list[str]:  # 鍒楀嚭灏氭湭瀹屾垚鐨勫墠缃换鍔★紱鏈€鏃╋細13.268 鈭?    incomplete = []  # 鏀堕泦鏈畬鎴愮殑渚濊禆 ID銆?    for dep_id in task.blockedBy:  # 閫愪釜妫€鏌ュ墠缃换鍔°€?        try:  # 楠岃瘉渚濊禆浠诲姟璺緞銆?            dep_path = _task_path(dep_id)  # 瑙ｆ瀽渚濊禆鏂囦欢璺緞銆?        except ValueError:  # 渚濊禆 ID 鏃犳晥鏃躲€?            incomplete.append(dep_id)  # 灏嗘棤鏁堜緷璧栬涓烘湭瀹屾垚銆?            continue  # 缁х画妫€鏌ュ叾浠栦緷璧栥€?        if not dep_path.exists() or load_task(dep_id).status != "completed":  # 渚濊禆鏂囦欢涓嶅瓨鍦ㄦ垨鐘舵€佹湭瀹屾垚鏃躲€?            incomplete.append(dep_id)  # 鍔犲叆鏈畬鎴愬垪琛ㄣ€?    return incomplete  # 杩斿洖闃诲浠诲姟鐨勪緷璧栥€?

def claim_task(task_id: str, owner: str = "agent") -> str:  # 鏍￠獙渚濊禆鍚庡皢浠诲姟鍒嗛厤缁欒礋璐ｄ汉锛涙渶鏃╋細10.234 鈭?    """Atomically claim one task and bind the owner's filesystem cwd.锝滀腑鏂囷細鍘熷瓙璁ら浠诲姟锛屽苟缁戝畾璐熻矗浜虹殑鏂囦欢绯荤粺宸ヤ綔鐩綍銆?""
    with task_store_lock():  # 鎸侀攣妫€鏌ュ拰鎸佷箙鍖栭鍙栥€?        task = load_task(task_id)  # 璇诲彇瑕侀鍙栫殑浠诲姟銆?        if task.status != "pending":  # 浠呭緟澶勭悊浠诲姟鍙鍙栥€?            return f"Task {task_id} is {task.status}, cannot claim"  # 杩斿洖褰撳墠鐘舵€侀敊璇€?        if task.owner:  # 宸茶缃礋璐ｄ汉鏃朵笉鑳藉啀娆￠鍙栥€?            return f"Task {task_id} is already owned by {task.owner}"  # 杩斿洖宸叉湁璐熻矗浜轰俊鎭€?        assignment = teammate_assignments.get(owner)  # 鏌ヨ璐熻矗浜虹殑宸ヤ綔鐩綍蹇収銆?        if assignment:  # 宸叉湁鍒嗛厤鏃朵笉鑳界珛鍗抽鍙栨柊浠诲姟銆?            return (f"Owner {owner} must finish the current work turn for "  # 鎻愮ず鍏堢粨鏉熷綋鍓嶅伐浣滆疆娆°€?                    f"{assignment['task_id']} before claiming another task")  # 闄勪笂褰撳墠鍒嗛厤鐨勪换鍔?ID銆?        current = _owner_in_progress(owner)  # 鏌ユ壘璐熻矗浜烘槸鍚﹁繕鏈夎繘琛屼腑浠诲姟銆?        if current:  # 瀛樺湪鏈畬鎴愪换鍔℃椂銆?            return (f"Owner {owner} must complete {current.id} before "  # 鎻愮ず鍏堝畬鎴愬綋鍓嶄换鍔°€?                    "claiming another task")  # 鎷掔粷棰嗗彇鍙︿竴浠诲姟銆?        if not can_start(task_id):  # 妫€鏌ユ墍鏈変緷璧栨槸鍚﹀畬鎴愩€?            return f"Blocked by: {_incomplete_dependencies(task)}"  # 杩斿洖灏氭湭瀹屾垚鐨勪緷璧栥€?        cwd, error = task_worktree_cwd(task)  # 瑙ｆ瀽骞堕獙璇佷换鍔″伐浣滅洰褰曘€?        if error:  # 宸ヤ綔鏍戠粦瀹氭湁璇椂銆?            return f"Cannot claim {task_id}: {error}"  # 鎷掔粷棰嗗彇骞惰繑鍥為敊璇€?        task.owner = owner  # 璁剧疆浠诲姟璐熻矗浜恒€?        task.status = "in_progress"  # 灏嗕换鍔℃敼涓鸿繘琛屼腑銆?        save_task(task)  # 鎸佷箙鍖栭鍙栫姸鎬併€?        teammate_assignments[owner] = {"task_id": task.id, "cwd": cwd}  # 淇濆瓨璐熻矗浜虹殑浠诲姟鍜岀洰褰曞揩鐓с€?        advance_assignment_version(owner)  # 鏇存柊鍒嗛厤鐗堟湰骞朵娇鏃у鎵瑰け鏁堛€?    print(f"  \033[36m[claim] {task.subject} -> in_progress (owner: {owner})\033[0m")  # 杈撳嚭棰嗗彇鐘舵€併€?    return f"Claimed {task.id} ({task.subject})"  # 杩斿洖棰嗗彇鎴愬姛淇℃伅銆?

def complete_task(task_id: str, owner: str = "agent") -> str:  # 灏嗚礋璐ｄ汉璁ら鐨勪换鍔℃爣璁板畬鎴愶紱鏈€鏃╋細10.248 鈭?    """Complete an assignment only when the caller owns it.锝滀腑鏂囷細浠呭厑璁镐换鍔¤礋璐ｄ汉灏嗚浠诲姟鏍囪瀹屾垚銆?""
    with task_store_lock():  # 鎸侀攣妫€鏌ュ苟鏇存柊浠诲姟鐘舵€併€?        task = load_task(task_id)  # 璇诲彇鐩爣浠诲姟銆?        if task.status != "in_progress":  # 鍙湁杩涜涓换鍔″彲浠ュ畬鎴愩€?            return f"Task {task_id} is {task.status}, cannot complete"  # 杩斿洖鐘舵€侀敊璇€?        if task.owner != owner:  # 浠呰礋璐ｄ汉鏈汉鍙互瀹屾垚浠诲姟銆?            return (f"Task {task_id} is owned by {task.owner}, "  # 璇存槑浠诲姟瀹為檯璐熻矗浜恒€?                    f"not {owner}; cannot complete")  # 鎷掔粷鍏朵粬璐熻矗浜哄畬鎴愩€?        gate = globals().get("plan_gates", {}).get(owner, "not_required")  # 鑾峰彇璐熻矗浜虹殑璁″垝瀹℃壒鐘舵€併€?        if gate in {"required", "pending", "rejected"}:  # 璁″垝浠嶉渶鎻愪氦銆佺瓑寰呮垨琚嫆缁濇椂銆?            return f"Task {task_id} cannot complete while plan status is {gate}"  # 闃绘浠诲姟瀹屾垚銆?        assignment = teammate_assignments.get(owner)  # 璇诲彇璐熻矗浜虹殑鐩綍蹇収銆?        if not assignment or assignment.get("task_id") != task.id:  # 蹇収涓嶅瓨鍦ㄦ垨涓庡綋鍓嶄换鍔′笉绗︽椂銆?            cwd, error = task_worktree_cwd(task)  # 閲嶆柊楠岃瘉浠诲姟宸ヤ綔鐩綍銆?            if error:  # 宸ヤ綔鏍戠粦瀹氭棤鏁堟椂銆?                return f"Task {task_id} cannot complete: {error}"  # 鎷掔粷瀹屾垚骞惰繑鍥為敊璇€?            teammate_assignments[owner] = {"task_id": task.id, "cwd": cwd}  # 鎭㈠褰撳墠浠诲姟鐨勭洰褰曞揩鐓с€?        task.status = "completed"  # 灏嗕换鍔℃爣璁颁负宸插畬鎴愩€?        save_task(task)  # 鎸佷箙鍖栧畬鎴愮姸鎬併€?        unblocked = [t.subject for t in list_tasks()  # 鏌ユ壘褰撳墠宸叉弧瓒充緷璧栫殑寰呭鐞嗕换鍔°€?                     if t.status == "pending" and t.blockedBy and can_start(t.id)]  # 浠呭垪鍑烘湁渚濊禆涓旂幇鍦ㄥ彲浠ュ紑濮嬬殑浠诲姟銆?    print(f"  \033[32m[complete] {task.subject}\033[0m")  # 杈撳嚭瀹屾垚鐘舵€併€?    msg = f"Completed {task.id} ({task.subject})"  # 鏋勯€犲畬鎴愭彁绀恒€?    if unblocked:  # 瀛樺湪鍙紑濮嬬殑渚濊禆浠诲姟鏃躲€?        msg += f"\nUnblocked: {', '.join(unblocked)}"  # 灏嗗叾鍚嶇О闄勫埌杩斿洖淇℃伅銆?        print(f"  \033[33m[unblocked] {', '.join(unblocked)}\033[0m")  # 鍦ㄧ粓绔緭鍑哄彲寮€濮嬬殑浠诲姟銆?    return msg  # 杩斿洖瀹屾垚淇℃伅銆?

# -- Task-bound Worktrees --锝滀换鍔″伐浣滄爲锛氱户鎵跨 13 绔狅紝鐢ㄧ嫭绔?Git worktree 闅旂骞惰浠诲姟銆?
WORKTREES_DIR = WORKDIR / ".worktrees"  # 宸ヤ綔鏍戦泦涓斁鍦ㄥ伐浣滃尯涓嬨€?WORKTREES_ROOT = WORKTREES_DIR.resolve()  # 缂撳瓨瑙勮寖鍖栧悗鐨勫伐浣滄爲鏍硅矾寰勩€?VALID_WORKTREE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")  # 闄愬埗鍚嶇О闀垮害鍜屽厑璁哥殑瀛楃銆?

def validate_worktree_name(name: str) -> str | None:  # 鏍￠獙 worktree 鍚嶇О鍜屼繚鐣欏瓧锛涙渶鏃╋細13.350 鈭?    if not isinstance(name, str) or not VALID_WORKTREE_NAME.fullmatch(name):  # 楠岃瘉鍚嶇О绫诲瀷鍜屾牸寮忋€?        return ("worktree name must be 1-64 letters, digits, dots, "  # 杩斿洖鏍煎紡瑕佹眰銆?                "underscores, or dashes, and start with a letter or digit")  # 璇存槑鍏佽鐨勫瓧绗﹀強棣栧瓧绗︺€?    if name in {".", ".."} or ".." in name:  # 绂佹璺緞绌胯秺褰㈠紡鐨勫悕绉般€?        return "worktree name cannot contain '..'"  # 杩斿洖淇濈暀瀛楃閿欒銆?    return None  # 鏍￠獙閫氳繃銆?

def _worktree_path(name: str) -> Path:  # 鐢熸垚鍙楅檺浜庡伐浣滄爲鏍圭洰褰曠殑璺緞锛涙渶鏃╋細13.359  鈭?    path = (WORKTREES_DIR / name).resolve()  # 鐢熸垚骞惰鑼冨寲宸ヤ綔鏍戣矾寰勩€?    if (not WORKTREES_ROOT.is_relative_to(WORKDIR.resolve())  # 纭繚宸ヤ綔鏍戞牴鐩綍浠嶅湪宸ヤ綔鍖哄唴銆?            or not path.is_relative_to(WORKTREES_ROOT)  # 纭繚鐩爣璺緞浣嶄簬宸ヤ綔鏍戞牴鐩綍鍐呫€?            or path == WORKTREES_ROOT):  # 涓嶈兘鎶婃牴鐩綍鏈韩浣滀负鐩爣銆?        raise ValueError(f"Worktree path escapes directory: {name!r}")  # 璺緞涓嶅畨鍏ㄦ椂鎷掔粷銆?    return path  # 杩斿洖瀹夊叏璺緞銆?

def _worktree_branch(name: str) -> str:  # 鐢熸垚闅旂浠诲姟浣跨敤鐨?Git 鍒嗘敮鍚嶏紱鏈€鏃╋細13.368  鈭?    return f"wt/{name}"  # 缁熶竴浣跨敤 wt 鍓嶇紑鍛藉悕鍒嗘敮銆?

def _run_git(args: list[str], cwd: Path | None = None) -> tuple[bool, str]:  # 鎵ц搴曞眰 Git 鍛戒护骞惰繑鍥炵姸鎬侊紱鏈€鏃╋細13.372  鈭?    """Run Git without shell interpolation and return (ok, combined output).锝滀腑鏂囷細涓嶇粡 Shell 鎻掑€兼墽琛?Git锛屽苟杩斿洖鐘舵€佸強鍚堝苟杈撳嚭銆?""
    try:  # 鎹曡幏杩涚▼鍚姩鍙婅秴鏃堕敊璇€?        result = subprocess.run(  # 閫氳繃瀛愯繘绋嬫墽琛?Git銆?            ["git", *args], cwd=cwd or WORKDIR,  # 浠ュ弬鏁板垪琛ㄨ皟鐢紝閬垮厤 Shell 鎻掑€笺€?            capture_output=True, text=True, errors="replace", timeout=30,  # 鏀堕泦鏂囨湰杈撳嚭骞堕檺鍒舵墽琛屾椂闂淬€?        )  # 缁撴潫瀛愯繘绋嬭皟鐢ㄣ€?    except (OSError, subprocess.TimeoutExpired) as exc:  # 澶勭悊绯荤粺閿欒鍜岃秴鏃躲€?        return False, f"{type(exc).__name__}: {exc}"  # 杩斿洖澶辫触鍙婇敊璇俊鎭€?    output = (result.stdout + result.stderr).strip()  # 鍚堝苟鏍囧噯杈撳嚭鍜岄敊璇緭鍑恒€?    return result.returncode == 0, output or "(no output)"  # 鏍规嵁閫€鍑虹爜杩斿洖鐘舵€佷笌杈撳嚭銆?

def run_git(args: list[str], cwd: Path | None = None) -> tuple[bool, str]:  # 鍦?Git 浠撳簱涓畨鍏ㄦ墽琛屽懡浠わ紱鏈€鏃╋細13.385 鈭?    """Run Git and bound only the text returned to the model.锝滀腑鏂囷細鎵ц Git锛屽苟浠呴檺鍒惰繑鍥炵粰妯″瀷鐨勬枃鏈暱搴︺€?""
    ok, output = _run_git(args, cwd)  # 璋冪敤搴曞眰 Git 鎵ц鍑芥暟銆?    return ok, output[:5000]  # 闄愬埗杩斿洖鏂囨湰闀垮害銆?

def _registered_worktrees() -> tuple[dict[Path, dict[str, str]], str | None]:  # 璇诲彇 Git 宸叉敞鍐岀殑 worktree锛涙渶鏃╋細13.391  鈭?    ok, output = _run_git(["worktree", "list", "--porcelain"])  # 璇诲彇 Git 鐨勬満鍣ㄥ彲瑙ｆ瀽宸ヤ綔鏍戝垪琛ㄣ€?    if not ok:  # 妫€鏌?Git 璋冪敤鏄惁鎴愬姛銆?        return {}, f"cannot read Git worktree registry: {output}"  # 杩斿洖娉ㄥ唽琛ㄨ鍙栭敊璇€?    entries: dict[Path, dict[str, str]] = {}  # 鎸夎鑼冨寲璺緞绱㈠紩娉ㄥ唽淇℃伅銆?    current: dict[str, str] = {}  # 淇濆瓨褰撳墠宸ヤ綔鏍戠殑瀛楁銆?    for line in output.splitlines() + [""]:  # 杩藉姞绌鸿浠ュ鐞嗘渶鍚庝竴鏉¤褰曘€?        if not line:  # 绌鸿琛ㄧず涓€鏉¤褰曠粨鏉熴€?            raw_path = current.get("worktree")  # 鑾峰彇褰撳墠璁板綍鐨勫伐浣滄爲璺緞銆?            if raw_path:  # 鍙繚瀛樺惈璺緞鐨勮褰曘€?                entries[Path(raw_path).resolve()] = current  # 灏嗗綋鍓嶈褰曞姞鍏ョ储寮曘€?            current = {}  # 寮€濮嬭В鏋愪笅涓€鏉¤褰曘€?            continue  # 璺宠繃鏈寰幆浣欎笅閮ㄥ垎銆?        key, _, value = line.partition(" ")  # 鎷嗗垎瀛楁鍚嶅拰瀛楁鍊笺€?        current[key] = value  # 璁板綍褰撳墠瀛楁銆?    return entries, None  # 杩斿洖娉ㄥ唽琛ㄥ拰绌洪敊璇€?

def _registered_worktree(name: str) -> tuple[Path | None, str | None]:  # 鏌ユ壘鎸囧畾鍚嶇О鐨勫凡娉ㄥ唽 worktree锛涙渶鏃╋細13.409  鈭?    try:  # 鍏堥獙璇佸苟瑙ｆ瀽鐩爣璺緞銆?        path = _worktree_path(name)  # 鑾峰彇鐩爣宸ヤ綔鏍戣矾寰勩€?    except ValueError as exc:  # 澶勭悊涓嶅畨鍏ㄨ矾寰勩€?        return None, str(exc)  # 鍚戣皟鐢ㄦ柟杩斿洖閿欒銆?    entries, error = _registered_worktrees()  # 璇诲彇 Git 娉ㄥ唽琛ㄣ€?    if error:  # 妫€鏌ユ敞鍐岃〃璇诲彇缁撴灉銆?        return None, error  # 鍚戣皟鐢ㄦ柟杩斿洖閿欒銆?    if path not in entries:  # 鐩爣椤诲凡鍦?Git 涓敞鍐屻€?        return None, f"worktree '{name}' is not registered with Git"  # 杩斿洖鏈敞鍐岄敊璇€?    if not path.is_dir():  # 娉ㄥ唽璺緞椤讳粛鏄洰褰曘€?        return None, f"worktree '{name}' is missing at {path}"  # 杩斿洖鐩綍缂哄け閿欒銆?    expected_branch = f"refs/heads/{_worktree_branch(name)}"  # 鏋勯€犻鏈熺殑瀹屾暣鍒嗘敮寮曠敤銆?    if entries[path].get("branch") != expected_branch:  # 妫€鏌ュ疄闄呭垎鏀槸鍚︿竴鑷淬€?        return None, (f"worktree '{name}' is not registered on expected "  # 杩斿洖鍒嗘敮涓嶅尮閰嶉敊璇€?                      f"branch '{_worktree_branch(name)}'")  # 闄勪笂棰勬湡鍒嗘敮鍚嶃€?    return path, None  # 杩斿洖宸查獙璇佽矾寰勩€?

def task_worktree_cwd(task: Task) -> tuple[Path, str | None]:  # 瑙ｆ瀽浠诲姟缁戝畾鐨?worktree 鐩綍锛涙渶鏃╋細13.428  鈭?    """Resolve a task cwd, failing closed for broken worktree bindings.锝滀腑鏂囷細瑙ｆ瀽浠诲姟宸ヤ綔鐩綍锛涘伐浣滄爲缁戝畾鎹熷潖鏃舵寜鎷掔粷绛栫暐澶勭悊銆?""
    if not task.worktree:  # 浠诲姟鏈粦瀹氬伐浣滄爲鏃躲€?        return WORKDIR, None  # 浣跨敤涓诲伐浣滃尯鐩綍銆?    path, error = _registered_worktree(task.worktree)  # 楠岃瘉浠诲姟缁戝畾鐨勫伐浣滄爲銆?    return (path or WORKDIR), error  # 浼犲洖鐩綍鍙婇敊璇紝鐢辫皟鐢ㄦ柟鎷掔粷閿欒璺緞銆?

def assignment_cwd(owner: str) -> Path:  # 鍙栧緱璐熻矗浜哄綋鍓嶄换鍔＄殑宸ヤ綔鐩綍锛涙渶鏃╋細13.436  鈭?    with task_lock:  # 鎸侀攣璇诲彇浠诲姟鍒嗛厤鐘舵€併€?        assignment = teammate_assignments.get(owner)  # 鏌ヨ璐熻矗浜哄凡鏈夌殑鐩綍蹇収銆?        task = _owner_in_progress(owner)  # 鏌ユ壘璐熻矗浜虹殑杩涜涓换鍔°€?        if task and (not assignment or assignment.get("task_id") != task.id):  # 鏂颁换鍔℃垨蹇収涓嶅尮閰嶆椂閲嶅缓蹇収銆?            cwd, error = task_worktree_cwd(task)  # 瑙ｆ瀽浠诲姟瀵瑰簲鐩綍銆?            if error:  # 缁戝畾寮傚父鏃舵嫆缁濈户缁€?                raise ValueError(error)  # 鍚戣皟鐢ㄦ柟鎶ュ憡閿欒銆?            assignment = {"task_id": task.id, "cwd": cwd}  # 璁板綍浠诲姟 ID 涓庡伐浣滅洰褰曘€?            teammate_assignments[owner] = assignment  # 淇濆瓨璐熻矗浜虹洰褰曞揩鐓с€?        elif not assignment:  # 鏃犺繘琛屼腑浠诲姟鍜屽揩鐓ф椂銆?            return WORKDIR  # 浣跨敤涓诲伐浣滃尯銆?        task = load_task(str(assignment["task_id"]))  # 閲嶆柊璇诲彇蹇収瀵瑰簲鐨勪换鍔°€?        if task.status not in {"in_progress", "completed"} or task.owner != owner:  # 纭浠诲姟鐘舵€佸拰璐熻矗浜轰粛鏈夋晥銆?            raise ValueError(f"Assignment for {owner} is no longer active")  # 鍒嗛厤澶辨晥鏃舵嫆缁濊闂€?        cwd, error = task_worktree_cwd(task)  # 閲嶆柊楠岃瘉浠诲姟宸ヤ綔鐩綍銆?        if error:  # 鍙戠幇缁戝畾閿欒鏃躲€?            raise ValueError(error)  # 鍚戣皟鐢ㄦ柟鎶ュ憡閿欒銆?        if cwd.resolve() != Path(assignment["cwd"]).resolve():  # 闃叉宸ヤ綔鐩綍鍦ㄥ垎閰嶆湡闂村彉鍖栥€?            raise ValueError(f"Assignment cwd changed for task {task.id}")  # 鐩綍鍙樺寲鏃舵嫆缁濊闂€?        return cwd  # 杩斿洖楠岃瘉鍚庣殑宸ヤ綔鐩綍銆?

def release_completed_assignment(owner: str) -> bool:  # 浠诲姟瀹屾垚鍚庨噴鏀捐礋璐ｄ汉鐩綍蹇収锛涙渶鏃╋細13.459 鈭?    """Release a completed cwd lease only at a model turn boundary.锝滀腑鏂囷細浠呭湪妯″瀷杞杈圭晫閲婃斁宸插畬鎴愪换鍔＄殑鐩綍绉熺害銆?""
    with task_lock:  # 鎸侀攣妫€鏌ョ洰褰曞揩鐓с€?        assignment = teammate_assignments.get(owner)  # 璇诲彇璐熻矗浜虹殑褰撳墠鍒嗛厤銆?        if not assignment:  # 娌℃湁鍒嗛厤鏃舵棤闇€閲婃斁銆?            return False  # 杩斿洖鏈噴鏀俱€?        task = load_task(str(assignment["task_id"]))  # 璇诲彇鍒嗛厤瀵瑰簲浠诲姟銆?        if task.status != "completed" or task.owner != owner:  # 鍙噴鏀捐璐熻矗浜哄凡瀹屾垚鐨勪换鍔°€?            return False  # 鏉′欢涓嶇鏃朵繚鐣欏垎閰嶃€?        teammate_assignments.pop(owner, None)  # 绉婚櫎宸ヤ綔鐩綍蹇収銆?        advance_assignment_version(owner)  # 鏇存柊鍒嗛厤鐗堟湰锛屼娇鏃у鎵瑰け鏁堛€?        if owner in globals().get("plan_gates", {}):  # 濡傛灉瀛樺湪璇ヨ礋璐ｄ汉鐨勮鍒掗棬鎺с€?            globals()["plan_gates"][owner] = "not_required"  # 灏嗚鍒掗棬鎺ч噸缃负涓嶉渶瑕併€?        return True  # 杩斿洖閲婃斁鎴愬姛銆?

def release_teammate_assignment(owner: str):  # 閲婃斁闃熷弸褰撳墠浠诲姟鍒嗛厤锛涙渶鏃╋細13.475 鈭?    """Return abandoned teammate work to the task board on thread exit.锝滀腑鏂囷細闃熷弸绾跨▼閫€鍑烘椂锛屽皢鏀惧純鐨勪换鍔￠€€鍥炰换鍔＄湅鏉裤€?""
    with task_lock:  # 鎸侀攣澶勭悊闃熷弸浠诲姟銆?        try:  # 鍗充娇浠诲姟澶勭悊澶辫触涔熸墽琛屾竻鐞嗐€?            task = _owner_in_progress(owner)  # 鏌ユ壘闃熷弸姝ｅ湪杩涜鐨勪换鍔°€?            if task:  # 瀛樺湪鏈畬鎴愪换鍔℃椂銆?                task.status = "pending"  # 灏嗕换鍔￠€€鍥炲緟澶勭悊鐘舵€併€?                task.owner = None  # 娓呴櫎鍘熻礋璐ｄ汉銆?                save_task(task)  # 淇濆瓨閫€鍥炲悗鐨勪换鍔°€?        finally:  # 鏃犺鏄惁鍑洪敊閮芥竻鐞嗗垎閰嶃€?            teammate_assignments.pop(owner, None)  # 绉婚櫎闃熷弸鐩綍蹇収銆?            advance_assignment_version(owner)  # 鏇存柊鐗堟湰骞朵娇鏃у鎵瑰け鏁堛€?            if owner in globals().get("plan_gates", {}):  # 濡傛灉瀛樺湪璁″垝闂ㄦ帶銆?                globals()["plan_gates"][owner] = "not_required"  # 閲嶇疆璁″垝闂ㄦ帶銆?

def create_worktree(name: str, task_id: str) -> str:  # 涓轰换鍔″垱寤虹嫭绔?Git 宸ヤ綔鏍戯紱鏈€鏃╋細13.491 鈭?    """Create and bind a dedicated worktree after all inputs validate.锝滀腑鏂囷細鎵€鏈夎緭鍏ユ牎楠岄€氳繃鍚庯紝鍒涘缓骞剁粦瀹氫笓鐢ㄥ伐浣滄爲銆?""
    error = validate_worktree_name(name)  # 鍏堟牎楠屽伐浣滄爲鍚嶇О銆?    if error:  # 鍚嶇О涓嶅悎娉曟椂鍋滄銆?        return f"Error: {error}"  # 杩斿洖鍚嶇О鏍￠獙閿欒銆?    try:  # 瑙ｆ瀽骞堕獙璇佽緭鍏ヨ矾寰勩€?        path = _worktree_path(name)  # 鐢熸垚鍙楅檺宸ヤ綔鏍戣矾寰勩€?        task_path = _task_path(task_id)  # 楠岃瘉浠诲姟 ID 骞惰幏鍙栦换鍔℃枃浠惰矾寰勩€?    except ValueError as exc:  # 鎹曡幏璺緞鎴栦换鍔?ID 閿欒銆?        return f"Error: {exc}"  # 杩斿洖杈撳叆閿欒銆?    branch = _worktree_branch(name)  # 鐢熸垚瀵瑰簲鍒嗘敮鍚嶃€?
    with task_lock:  # 鎸侀攣妫€鏌ュ苟鏇存柊浠诲姟鍒嗛厤銆?        if not task_path.exists():  # 纭浠诲姟鏂囦欢瀛樺湪銆?            return f"Error: Task {task_id} not found"  # 浠诲姟涓嶅瓨鍦ㄦ椂杩斿洖閿欒銆?        task = load_task(task_id)  # 璇诲彇浠诲姟璁板綍銆?        if task.status != "pending" or task.owner is not None:  # 鍙厑璁哥粦瀹氭湭棰嗗彇鐨勫緟澶勭悊浠诲姟銆?            return f"Error: Task {task_id} must be pending and unowned"  # 鐘舵€佷笉绗︽椂鎷掔粷鍒涘缓銆?        if task.worktree:  # 妫€鏌ヤ换鍔℃槸鍚﹀凡鏈夊伐浣滄爲銆?            return f"Error: Task {task_id} already uses worktree '{task.worktree}'"  # 绂佹閲嶅缁戝畾銆?        if any(t.worktree == name for t in list_tasks() if t.id != task_id):  # 妫€鏌ュ叾浠栦换鍔℃槸鍚﹀凡缁戝畾鍚屽悕宸ヤ綔鏍戙€?            return f"Error: Worktree '{name}' is already bound to another task"  # 鍚屽悕缁戝畾瀛樺湪鏃舵嫆缁濄€?        if path.exists():  # 妫€鏌ョ洰鏍囪矾寰勬槸鍚﹀凡瀛樺湪銆?            return f"Error: Worktree path already exists: {path}"  # 閬垮厤瑕嗙洊鐜版湁鏂囦欢銆?
        ok, root = run_git(["rev-parse", "--show-toplevel"])  # 鏌ヨ褰撳墠 Git 浠撳簱鏍圭洰褰曘€?        if not ok or Path(root).resolve() != WORKDIR.resolve():  # 瑕佹眰宸ヤ綔鐩綍鏈韩灏辨槸浠撳簱鏍圭洰褰曘€?            return "Error: Working directory must be the root of a Git repository"  # 涓嶆弧瓒虫潯浠舵椂鎷掔粷鍒涘缓銆?        ok, branch_check = run_git(["check-ref-format", "--branch", branch])  # 鏍￠獙鐢熸垚鐨勫垎鏀悕銆?        if not ok:  # 妫€鏌?Git 杩斿洖缁撴灉銆?            return f"Error: Invalid worktree branch '{branch}': {branch_check}"  # 鎶ュ憡鏃犳晥鍒嗘敮鍚嶃€?        exists, _ = run_git(["show-ref", "--verify", "--quiet",  # 妫€鏌ョ洰鏍囧垎鏀槸鍚﹀瓨鍦ㄣ€?                             f"refs/heads/{branch}"])  # 浣跨敤瀹屾暣鍒嗘敮寮曠敤杩涜楠岃瘉銆?        if exists:  # 宸插瓨鍦ㄦ椂涓嶈兘閲嶅鍒涘缓銆?            return f"Error: Branch '{branch}' already exists"  # 杩斿洖鍒嗘敮鍐茬獊閿欒銆?        entries, registry_error = _registered_worktrees()  # 璇诲彇 Git 宸叉敞鍐屽伐浣滄爲銆?        if registry_error:  # 妫€鏌ユ敞鍐岃〃璇诲彇閿欒銆?            return f"Error: {registry_error}"  # 杩斿洖娉ㄥ唽琛ㄩ敊璇€?        if path in entries:  # 妫€鏌ョ洰鏍囪矾寰勬槸鍚﹀凡娉ㄥ唽銆?            return f"Error: Worktree path is already registered: {path}"  # 閬垮厤澶嶇敤宸叉敞鍐岃矾寰勩€?
        WORKTREES_DIR.mkdir(parents=True, exist_ok=True)  # 纭繚宸ヤ綔鏍戠埗鐩綍瀛樺湪銆?        ok, result = run_git(["worktree", "add", "-b", branch,  # 鍒涘缓鍒嗘敮骞舵坊鍔?Git 宸ヤ綔鏍戙€?                              str(path), "HEAD"])  # 浠庡綋鍓?HEAD 妫€鍑哄埌鐩爣鐩綍銆?        if not ok:  # 妫€鏌?Git 鍛戒护鏄惁鎴愬姛銆?            entries, registry_error = _registered_worktrees()  # 澶辫触鍚庨噸鏂拌鍙栨敞鍐岃〃銆?            branch_exists, _ = run_git(  # 妫€鏌?Git 鏄惁宸茬暀涓嬪垎鏀€?                ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]  # 鏌ヨ棰勬湡鍒嗘敮寮曠敤銆?            )  # 缁撴潫鍒嗘敮妫€鏌ャ€?            artifacts = []  # 鏀堕泦鍙兘娈嬬暀鐨?Git 浜х墿銆?            if path.exists():  # 妫€鏌ユ鍑虹洰褰曟槸鍚﹀瓨鍦ㄣ€?                artifacts.append(f"checkout path '{path}'")  # 璁板綍娈嬬暀鐩綍銆?            if registry_error is None and path in entries:  # 娉ㄥ唽琛ㄥ彲璇讳笖璺緞浠嶅湪鍏朵腑銆?                artifacts.append("registered Git worktree")  # 璁板綍娈嬬暀鐨勫伐浣滄爲娉ㄥ唽椤广€?            if branch_exists:  # 妫€鏌ュ垎鏀槸鍚﹀凡缁忓垱寤恒€?                artifacts.append(f"branch '{branch}'")  # 璁板綍娈嬬暀鍒嗘敮銆?            if artifacts:  # 瀛樺湪娈嬬暀鏃舵姤鍛婇儴鍒嗘搷浣溿€?                return (  # 杩斿洖浜哄伐鎭㈠鎻愮ず銆?                    "Partial operation: git worktree add reported an error "  # 璇存槑 Git 鎶ラ敊鏃跺彲鑳藉凡鐣欎笅浜х墿銆?                    f"after leaving {', '.join(artifacts)}. Task {task_id} "  # 鍒楀嚭浜х墿鍜屽搴斾换鍔°€?                    "remains unbound and no Git data was deleted. Run "  # 璇存槑浠诲姟鏈粦瀹氫笖娌℃湁鍒犻櫎 Git 鏁版嵁銆?                    f"`git worktree list`, inspect '{path}' and '{branch}', "  # 鎻愮ず妫€鏌ユ敞鍐岃〃銆佺洰褰曞拰鍒嗘敮銆?                    "then keep or remove those artifacts manually after "  # 鎻愮ず浜哄伐鍐冲畾淇濈暀鎴栫Щ闄ゃ€?                    f"preserving any work. Git error: {result}"  # 鎻愰啋鍏堜繚鐣欏伐浣滃苟闄?Git 閿欒銆?                )  # 缁撴潫閮ㄥ垎鎿嶄綔鎻愮ず銆?            return f"Git error: {result}"  # 鏃犲凡妫€娴嬫畫鐣欐椂杩斿洖 Git 閿欒銆?
        try:  # 灏濊瘯灏嗘柊宸ヤ綔鏍戠粦瀹氬埌浠诲姟銆?            task.worktree = name  # 鍐欏叆宸ヤ綔鏍戝悕绉般€?            save_task(task)  # 鎸佷箙鍖栦换鍔＄粦瀹氥€?        except Exception as exc:  # 鎹曡幏浠诲姟缁戝畾淇濆瓨閿欒銆?            return (f"Partial success: Worktree '{name}' was created at "  # 鎶ュ憡宸ヤ綔鏍戝凡鍒涘缓浣嗙粦瀹氬け璐ャ€?                    f"{path} on branch '{branch}', but task binding failed: "  # 闄勪笂鐩綍鍜屽垎鏀€?                    f"{exc}. Git data was retained for manual recovery.")  # 淇濈暀 Git 鏁版嵁渚涗汉宸ユ仮澶嶃€?
    print(f"  \033[33m[worktree] created: {name} at {path}\033[0m")  # 鍦ㄧ粓绔樉绀哄垱寤虹粨鏋溿€?    return f"Worktree '{name}' created at {path} for task {task_id}"  # 杩斿洖宸ヤ綔鏍戝拰浠诲姟淇℃伅銆?

def remove_worktree(name: str, discard_changes: bool = False) -> str:  # 瀹夊叏绉婚櫎浠诲姟宸ヤ綔鏍戝苟淇濈暀瀵瑰簲鍒嗘敮锛涙渶鏃╋細13.570
    """Remove a registered checkout while always retaining its branch.锝滀腑鏂囷細绉婚櫎宸叉敞鍐岀殑妫€鍑虹洰褰曪紝浣嗗缁堜繚鐣欏搴斿垎鏀€?""
    error = validate_worktree_name(name)  # 鍏堟牎楠屽伐浣滄爲鍚嶇О銆?    if error:  # 鍚嶇О涓嶅悎娉曟椂鍋滄銆?        return f"Error: {error}"  # 杩斿洖鏍￠獙閿欒銆?    with task_lock:  # 鎸侀攣妫€鏌ヤ换鍔″拰鐩綍绉熺害銆?        path, error = _registered_worktree(name)  # 楠岃瘉宸ヤ綔鏍戝凡娉ㄥ唽涓斿垎鏀纭€?        if error:  # 妫€鏌ラ獙璇侀敊璇€?            return f"Error: {error}"  # 杩斿洖楠岃瘉閿欒銆?        bound = [task for task in list_tasks() if task.worktree == name]  # 鏌ユ壘缁戝畾璇ュ伐浣滄爲鐨勪换鍔°€?        if not bound:  # 蹇呴』瀛樺湪浠诲姟缁戝畾銆?            return f"Error: Worktree '{name}' is not bound to a task"  # 鏃犵粦瀹氭椂鎷掔粷绉婚櫎銆?        active = [task for task in bound if task.status != "completed"]  # 鎵惧嚭鏈畬鎴愮殑缁戝畾浠诲姟銆?        if active:  # 娲诲姩浠诲姟瀛樺湪鏃跺仠姝€?            return (f"Error: Worktree '{name}' is bound to active task "  # 鎻愮ず宸ヤ綔鏍戜粛鏈夋椿鍔ㄤ换鍔°€?                    f"{active[0].id}; complete it before removal")  # 瑕佹眰鍏堝畬鎴愯浠诲姟銆?        leased = [owner for owner, assignment in teammate_assignments.items()  # 鏌ユ壘姝ｅ湪浣跨敤璇ョ洰褰曠殑璐熻矗浜恒€?                  if Path(assignment["cwd"]).resolve() == path.resolve()]  # 姣旇緝瑙勮寖鍖栧悗鐨勫伐浣滅洰褰曘€?        if leased:  # 瀛樺湪鐩綍绉熺害鏃跺仠姝€?            return (f"Error: Worktree '{name}' is still in use by "  # 鎻愮ず宸ヤ綔鏍戜粛鍦ㄤ娇鐢ㄣ€?                    f"{', '.join(sorted(leased))}; wait for the turn to end")  # 瑕佹眰绛夊緟鐩稿叧杞缁撴潫銆?        with globals().get("background_lock", threading.Lock()):  # 鎸佸悗鍙颁换鍔￠攣妫€鏌ヨ繍琛岀姸鎬併€?            running = [task for task in globals().get("background_tasks", {}).values()  # 閬嶅巻鍚庡彴浠诲姟銆?                       if task.get("status") == "running"  # 绛涢€夎繍琛屼腑鐨勪换鍔°€?                       and task.get("cwd")  # 鍙鏌ヨ褰曚簡鐩綍鐨勪换鍔°€?                       and Path(task["cwd"]).resolve() == path.resolve()]  # 绛涢€変娇鐢ㄨ宸ヤ綔鏍戠洰褰曠殑浠诲姟銆?        if running:  # 瀛樺湪杩愯涓殑鍚庡彴鍛戒护鏃跺仠姝€?            return (f"Error: Worktree '{name}' has a running background command; "  # 鎶ュ憡宸ヤ綔鏍戜粛鏈夊悗鍙板懡浠ゃ€?                    "wait for it to finish")  # 瑕佹眰绛夊緟鍛戒护缁撴潫銆?
        ok, status = run_git(  # 閫氳繃 Git 妫€鏌ュ伐浣滄爲鐘舵€併€?            ["status", "--porcelain", "--ignored"], cwd=path  # 鍖呭惈鏈窡韪拰琚拷鐣ョ殑鏂囦欢銆?        )  # 缁撴潫鐘舵€佹煡璇€?        if not ok:  # 鐘舵€佹鏌ュけ璐ユ椂鎷掔粷绉婚櫎銆?            return f"Error: Cannot verify worktree '{name}' status: {status}"  # 杩斿洖妫€鏌ラ敊璇€?        if status != "(no output)" and not discard_changes:  # 鏈夊彉鏇翠笖鏈厑璁镐涪寮冩椂銆?            changed = len([line for line in status.splitlines() if line.strip()])  # 缁熻鐘舵€佽緭鍑轰腑鐨勫彉鏇磋銆?            return (f"Error: Worktree '{name}' has {changed} uncommitted "  # 鎻愮ず瀛樺湪鏈彁浜ゅ彉鏇淬€?                    "change(s); preserve or discard them manually")  # 瑕佹眰浜哄伐淇濈暀鎴栦涪寮冨彉鏇淬€?
        args = ["worktree", "remove"]  # 鍑嗗宸ヤ綔鏍戠Щ闄ゅ懡浠ゃ€?        if discard_changes:  # 鏄惧紡鍏佽涓㈠純鍙樻洿鏃躲€?            args.append("--force")  # 娣诲姞 Git 寮哄埗绉婚櫎鍙傛暟銆?        args.append(str(path))  # 鎸囧畾宸查獙璇佺殑鐩爣璺緞銆?        ok, result = run_git(args)  # 鎵ц宸ヤ綔鏍戠Щ闄ゃ€?        if not ok:  # 妫€鏌?Git 杩斿洖鐘舵€併€?            return f"Git error: {result}"  # 杩斿洖绉婚櫎閿欒銆?
        try:  # 绉婚櫎鎴愬姛鍚庢竻鐞嗕换鍔＄粦瀹氥€?            for task in bound:  # 閬嶅巻缁戝畾璇ュ伐浣滄爲鐨勪换鍔°€?                task.worktree = None  # 娓呯┖宸ヤ綔鏍戝悕绉般€?                save_task(task)  # 淇濆瓨浠诲姟鍙樻洿銆?        except Exception as exc:  # 鎹曡幏娓呯悊缁戝畾鏃剁殑閿欒銆?            return (f"Partial success: Worktree '{name}' was removed and "  # 璇存槑宸ヤ綔鏍戝凡琚Щ闄ゃ€?                    f"branch '{_worktree_branch(name)}' retained, but task "  # 璇存槑鍒嗘敮浠嶈淇濈暀銆?                    f"unbinding failed: {exc}. Manual recovery is required.")  # 鎶ュ憡瑙ｇ粦澶辫触骞惰姹備汉宸ユ仮澶嶃€?
    print(f"  \033[33m[worktree] removed: {name}; branch retained\033[0m")  # 杈撳嚭绉婚櫎缁撴灉鍙婂垎鏀繚鐣欑姸鎬併€?    return f"Worktree '{name}' removed; branch '{_worktree_branch(name)}' retained"  # 杩斿洖绉婚櫎鎴愬姛淇℃伅銆?

# -- Skill Loading --锝滄妧鑳藉姞杞斤細婧愯嚜绗?7 绔狅紱绗?15 绔犳敼涓烘壂鎻?SKILL.md 骞剁撼鍏ョ粺涓€鎻愮ず璇嶃€?
SKILL_REGISTRY: dict[str, dict] = {}  # 缂撳瓨鎶€鑳藉悕绉般€佺畝浠嬪拰鍘熸枃锛涚洰褰曞睍绀轰笌瀹屾暣鍔犺浇鍏变韩杩欎竴浠界储寮曘€?

def _parse_frontmatter(text: str) -> tuple[dict, str]:  # 瑙ｆ瀽 SKILL.md 鐨?YAML 澶村拰姝ｆ枃锛涙渶鏃╋細15.716 鈭?    lines = text.splitlines(keepends=True)  # 淇濈暀鎹㈣鎷嗗垎锛屽悗缁噸缁勬鏂囨椂涓嶇牬鍧?SKILL.md 鐨勫師濮嬫牸寮忋€?    if not lines or lines[0].rstrip("\r\n") != "---":  # 娌℃湁 YAML 璧峰鍒嗛殧绗︽椂锛屾妸鏁翠釜鏂囦欢瑙嗕负鏅€氭妧鑳借鏄庛€?        return {}, text  # 杩斿洖绌哄厓鏁版嵁浣嗕繚鐣欏師鏂囷紝浣挎棤 frontmatter 鐨勬妧鑳戒粛鍙娇鐢ㄣ€?
    closing_index = next(  # 鏌ユ壘棣栦釜缁撴潫鍒嗛殧绗︼紝闄愬畾 YAML 澶寸殑鑼冨洿銆?        (index for index, line in enumerate(lines[1:], start=1)  # 浠庣浜岃寮€濮嬶紝閬垮厤鎶婅捣濮嬬璇涓虹粨鏉熺銆?         if line.rstrip("\r\n") == "---"),  # 鍙帴鍙楁暣琛屽垎闅旂锛屾鏂囦腑鐨勮繛缁煭妯嚎涓嶄細璇懡涓€?        None,  # 鎵句笉鍒版椂浠?None 琛ㄧず frontmatter 涓嶅畬鏁淬€?    )
    if closing_index is None:  # 涓嶅畬鏁?YAML 澶翠笉搴斿悶鎺夋妧鑳芥鏂囨垨闃绘柇鍏ㄩ儴鎶€鑳芥壂鎻忋€?        return {}, text  # 瀹夊叏闄嶇骇涓烘棤鍏冩暟鎹枃妗ｃ€?
    frontmatter = "".join(lines[1:closing_index])  # 浠呮嫾鎺ヤ袱涓垎闅旂涔嬮棿鐨?YAML 閰嶇疆銆?    body = "".join(lines[closing_index + 1:]).strip()  # 姝ｆ枃鍘婚櫎棣栧熬绌虹櫧锛屼究浜庢彁鍙栨爣棰樹綔涓哄悗澶囩畝浠嬨€?    try:  # 鍗曚釜鎶€鑳芥牸寮忛敊璇笉搴斿鑷存暣涓 15 绔犺繍琛屾椂鏃犳硶鍚姩銆?        meta = yaml.safe_load(frontmatter) or {}  # 浣跨敤 safe_load锛岀姝?YAML 鏋勯€犱换鎰?Python 瀵硅薄銆?    except yaml.YAMLError:  # 鎹曡幏璇硶閿欒骞剁户缁妸璇ユ枃浠跺綋浣滄棤鍏冩暟鎹妧鑳姐€?        meta = {}  # 娓呯┖涓嶅彲淇＄殑閮ㄥ垎瑙ｆ瀽缁撴灉銆?    if not isinstance(meta, dict):  # 鎶€鑳藉ご蹇呴』鏄敭鍊兼槧灏勶紝鍒楄〃鎴栨爣閲忔棤娉曟彁渚?name/description銆?        meta = {}  # 绫诲瀷涓嶇鍚堢害瀹氭椂缁熶竴闄嶇骇銆?    return meta, body  # 鍚屾椂杩斿洖缁撴瀯鍖栧厓鏁版嵁鍜屽彲璇绘鏂囷紝渚涙壂鎻忓櫒閫夋嫨淇℃伅鏉ユ簮銆?

def scan_skills():  # 鎵弿骞惰В鏋愭墍鏈?SKILL.md锛涙渶鏃╋細15.740 鈭?    SKILL_REGISTRY.clear()  # 姣忔鎵弿浠庣湡瀹炴枃浠剁郴缁熼噸寤猴紝閬垮厤宸插垹闄ゆ妧鑳芥畫鐣欏湪缂撳瓨涓€?    if not SKILLS_DIR.exists():  # skills 鐩綍鏄彲閫夎兘鍔涳紝涓嶅瓨鍦ㄦ椂涓?Agent 浠嶅簲姝ｅ父杩愯銆?        return  # 淇濇寔绌烘敞鍐岃〃锛岀敱 list_skills 缁欏嚭鏄庣‘鎻愮ず銆?    skills_root = SKILLS_DIR.resolve()  # 鍥哄寲鍙俊鏍圭洰褰曪紝鍚庣画鐢ㄧ湡瀹炶矾寰勯樆姝㈢鍙烽摼鎺ヨ秺鐣屻€?    for directory in sorted(SKILLS_DIR.iterdir()):  # 鎺掑簭淇濊瘉鎻愮ず璇嶄腑鎶€鑳介『搴忕ǔ瀹氾紝渚夸簬璋冭瘯鍜屾祴璇曘€?        if not directory.is_dir():  # 鏍圭洰褰曚腑鐨勬櫘閫氭枃浠朵笉鏄竴涓妧鑳藉寘銆?            continue  # 鍙壂鎻忎竴灞傚瓙鐩綍锛岄伩鍏嶆棤杈圭晫閫掑綊鍜屾剰澶栬鍙栭」鐩枃浠躲€?        manifest = directory / "SKILL.md"  # 绾﹀畾姣忎釜鎶€鑳戒互 SKILL.md 浣滀负鍞竴鍏ュ彛銆?        if not manifest.exists():  # 娌℃湁娓呭崟鐨勭洰褰曚笉鍏峰鍙緵妯″瀷閬靛惊鐨勬妧鑳借鏄庛€?            continue  # 蹇界暐杈呭姪鐩綍鑰屼笉鏄鏁翠釜鎵弿澶辫触銆?        if not manifest.resolve().is_relative_to(skills_root):  # 瑙ｆ瀽绗﹀彿閾炬帴鍚庡啀娆＄‘璁ゆ枃浠朵粛浣嶄簬鎶€鑳芥牴鐩綍銆?            continue  # 鎷掔粷鍊熷姪閾炬帴璇诲彇宸ヤ綔鍖哄閮ㄥ唴瀹广€?        raw = manifest.read_text(encoding="utf-8")  # 瀹屾暣淇濈暀鎶€鑳藉師鏂囷紝鐪熸璋冪敤鎶€鑳芥椂闇€瑕佸叏閮ㄦ寚浠ゃ€?        meta, body = _parse_frontmatter(raw)  # 鍒嗙鐢ㄤ簬鐩綍灞曠ず鐨勫厓鏁版嵁涓庢鏂囥€?        raw_name = meta.get("name")  # 鍚嶇О浼樺厛閲囩敤浣滆€呭湪 YAML 涓０鏄庣殑绋冲畾鏍囪瘑銆?        name = raw_name.strip() if isinstance(raw_name, str) else ""  # 鍙帴鍙楀瓧绗︿覆骞跺幓鎺夎杈撳叆鐨勭┖鐧姐€?        name = name or directory.name  # 鏈０鏄庡悕绉版椂鐢ㄧ洰褰曞悕鍏滃簳锛屼繚璇佹瘡涓妧鑳戒粛鍙 load_skill 瀹氫綅銆?        raw_desc = meta.get("description")  # 绠€浠嬬敤浜庢笎杩涙姭闇查樁娈靛府鍔╂ā鍨嬪垽鏂妧鑳芥槸鍚︾浉鍏炽€?        desc = raw_desc.strip() if isinstance(raw_desc, str) else ""  # 鎷掔粷闈炲瓧绗︿覆鎻忚堪锛岄伩鍏嶆彁绀鸿瘝鍑虹幇澶嶆潅瀵硅薄銆?        desc = desc or body.split("\n", 1)[0].lstrip("#").strip()  # 鏃犳樉寮忕畝浠嬫椂鍙栨鏂囬琛屽苟鍘绘帀 Markdown 鏍囬绗︺€?        SKILL_REGISTRY[name] = {  # 浠ユ渶缁堝悕绉板缓绔嬪彲鐩存帴鏌ヨ鐨勬妧鑳借褰曘€?            "name": name,  # 淇濆瓨瑙勮寖鍖栧悕绉帮紝渚涚洰褰曡緭鍑轰娇鐢ㄣ€?            "description": desc,  # 鎻愮ず璇嶅彧甯搁┗鐭畝浠嬶紝鎺у埗绯荤粺鎻愮ず璇嶄綋绉€?            "content": raw,  # 鍘熸枃寤惰繜鍒?load_skill 璋冪敤鍚庢墠杩涘叆妯″瀷涓婁笅鏂囥€?        }


scan_skills()  # 鍚姩鏃跺缓绔嬫妧鑳界洰褰曪紱杩愯涓殑姣忚疆鎻愮ず璇嶇洿鎺ヨ鍙栬缂撳瓨銆?

def list_skills() -> str:  # 杈撳嚭鍙敤鎶€鑳界洰褰曪紱鏈€鏃╋細15.771 鈭?    if not SKILL_REGISTRY:  # 绌虹洰褰曚篃杩斿洖鍙鏂囨湰锛岄伩鍏嶆彁绀鸿瘝鍑虹幇妯＄硦鐨勭┖鐧藉尯娈点€?        return "锛堟湭鍙戠幇鍙敤鎶€鑳斤級"  # 鏄庣‘鍛婅瘔妯″瀷褰撳墠娌℃湁鍙姞杞芥妧鑳姐€?    return "\n".join(  # 姣忎釜鎶€鑳藉帇缂╀负鍗曡鐩綍椤癸紝瀹炵幇鈥滃厛鍙戠幇銆佸悗鍔犺浇鈥濄€?        f"- {skill['name']}: {skill['description']}"  # 鍚嶇О鐢ㄤ簬宸ュ叿鍙傛暟锛岀畝浠嬬敤浜庣浉鍏虫€у垽鏂€?        for skill in SKILL_REGISTRY.values())  # 娌跨敤鎵弿鏃剁殑绋冲畾椤哄簭杈撳嚭銆?

def load_skill(name: str) -> str:  # 鎸夊悕绉拌鍙栧畬鏁存妧鑳借鏄庯紱鏈€鏃╋細15.779 鈭?    skill = SKILL_REGISTRY.get(name)  # 绮剧‘鎸夌洰褰曚腑灞曠ず鐨勫悕绉版煡鎵撅紝閬垮厤妯″瀷鍔犺浇鐩镐技浣嗛敊璇殑鎶€鑳姐€?    if not skill:  # 鏈壘鍒版椂涓嶆姏寮傚父锛屽洜涓哄伐鍏烽敊璇篃闇€瑕佷綔涓虹粨鏋滃弽棣堢粰妯″瀷鑷垜淇銆?        available = ", ".join(SKILL_REGISTRY.keys()) or "(none)"  # 闄勪笂鍚堟硶鍊欓€夛紝鍑忓皯涓嬩竴娆¤皟鐢ㄧ户缁寽閿欍€?        return f"Skill not found: {name}. Available: {available}"  # 浠ユ櫘閫氬伐鍏风粨鏋滄姤鍛婂け璐ワ紝Agent 寰幆鍙户缁€?    return skill["content"]  # 杩斿洖瀹屾暣 SKILL.md锛岃妯″瀷鍙湪纭鐩稿叧鍚庢壙鎷呭叾涓婁笅鏂囨垚鏈€?

# -- Prompt Assembly --锝滄彁绀鸿瘝缁勮锛氭墿灞曠 14 绔犵殑鍔ㄦ€佹彁绀鸿瘝锛屾眹鎬荤 7銆?銆?3銆?4 绔犵殑鎶€鑳姐€佽蹇嗐€佸洟闃熶笌 MCP 鐘舵€併€?
PROMPT_SECTIONS = {  # 灏嗙ǔ瀹氳鍒欐寜鑱岃矗鎷嗗垎锛屼究浜庣 15 绔犳寜瀹炴椂鐘舵€佸姩鎬侀噸缁勶紝鑰屼笉鏄淮鎶や竴娈靛法鍨嬫彁绀鸿瘝銆?鈭?    "identity": "浣犳槸涓€涓紪绋?Agent銆傜洿鎺ラ噰鍙栬鍔紝涓嶈鍙仛瑙ｉ噴銆?,  # 韬唤娈靛彧绾︽潫鎬讳綋琛屼负锛岄伩鍏嶄笌鍏蜂綋宸ュ叿鍗忚鑰﹀悎銆?    "tools": "鍙敤宸ュ叿锛歜ash銆乺ead_file銆亀rite_file銆乪dit_file銆乬lob銆?  # 宸ュ叿娈靛憡璇夋ā鍨嬪唴缃兘鍔涘強鍔ㄦ€?MCP 鍛藉悕瑙勫垯銆?             "todo_write, task, load_skill, compact, "  # 鍒楀嚭寰呭姙銆佸瓙 Agent銆佹妧鑳藉拰鍘嬬缉宸ュ叿銆?             "create_task, update_task, list_tasks, get_task, claim_task, "  # 鍒楀嚭浠诲姟鍒涘缓銆佷緷璧栧強鏌ヨ宸ュ叿銆?             "complete_task, "  # 鍒楀嚭浠诲姟瀹屾垚宸ュ叿銆?             "schedule_cron, list_crons, cancel_cron, "  # 鍒楀嚭瀹氭椂浠诲姟宸ュ叿銆?             "spawn_teammate, list_teammates, send_message, "  # 鍒楀嚭闃熷弸鍒涘缓銆佹煡璇㈠拰娑堟伅宸ュ叿銆?             "request_shutdown, request_plan, review_plan, "  # 鍒楀嚭鍏抽棴鍙婅鍒掑鎵瑰伐鍏枫€?             "create_worktree, "  # 鍒楀嚭宸ヤ綔鏍戝伐鍏枫€?             "connect_mcp銆侻CP 宸ュ叿缁熶竴浣跨敤 mcp__{server}__{tool} 鍓嶇紑銆?,  # 璇存槑 MCP 宸ュ叿鍚嶇О鍓嶇紑銆?    "tasks": (  # 浠诲姟娈靛浐鍖栫 10銆?3 绔犵殑鍏抽敭椤哄簭锛氬厛鍙栧緱鐪熷疄 ID锛屽啀寤虹珛渚濊禆銆?        "鍏堝垱寤哄叏閮ㄤ换鍔¤妭鐐广€傚彧鏈夊湪 create_task 杩斿洖杩愯鏃剁敓鎴愮殑鐪熷疄 ID 鍚庯紝"  # 瑕佹眰鍏堝垱寤轰换鍔¤妭鐐瑰苟鍙栧緱鐪熷疄 ID銆?        "鎵嶈兘浣跨敤杩欎簺鍑嗙‘ ID 璋冪敤 update_task 娣诲姞渚濊禆鍏崇郴銆?  # 浣跨敤鐪熷疄 ID 娣诲姞浠诲姟渚濊禆銆?        "鍙湁 Lead 鍙互淇敼浠诲姟渚濊禆銆?  # 闄愬畾浠诲姟渚濊禆鐢?Lead 淇敼銆?    ),  # 缁撴潫浠诲姟瑙勫垯娈点€?    "teams": (  # 鍥㈤槦娈甸泦涓害鏉熷娲俱€佸伐浣滄爲鍜屽叧闂祦绋嬶紝闃叉妯″瀷鎶婂苟琛岃兘鍔涘綋浣滄棤鏉′欢鎺堟潈銆?        "褰撳苟琛屽鐞嗙‘鏈夊府鍔╂椂锛屽厛鎻愬嚭鑱岃矗娓呮櫚鐨勫皬鍨嬪洟闃熸柟妗堝苟绛夊緟鐢ㄦ埛纭銆?  # 骞惰鏈夊府鍔╂椂鍏堟彁鍑烘柟妗堝苟绛夊緟纭銆?        "鐢ㄦ埛纭鍓嶄笉寰楄皟鐢?spawn_teammate銆傜‘璁ゅ悗锛屼负姣忛」鍙嫭绔嬪苟琛岀殑淇敼鍒涘缓涓€涓?Task銆?  # 纭鍚庡垱寤洪槦鍙嬪強鐙珛浠诲姟銆?        "鍒嗘淳宸插氨缁伐浣滄椂锛屽皢 task_id 浼犵粰 spawn_teammate锛涘彧鏈夊湪鐙珛宸ヤ綔鐩綍鑳藉閬垮厤缂栬緫鍐茬獊鏃讹紝"  # 鍒嗘淳鏃朵紶鍏ヤ换鍔?ID 骞惰瘎浼扮洰褰曢殧绂汇€?        "鎵嶅垱寤轰笌浠诲姟缁戝畾鐨?worktree銆傞槦鍙嬪繀椤诲畬鎴愬綋鍓?Task 鍚庢墠鑳借棰嗗彟涓€涓换鍔°€?  # 鎸夐渶鍒涘缓宸ヤ綔鏍戝苟闄愬埗闃熷弸鍚屾椂璁ら鐨勪换鍔°€?        "worktree 鍙敼鍙樺伐鍏风殑榛樿 cwd锛屽苟涓嶆槸瀹夊叏娌欑銆傜Щ闄?worktree 鐨勬潈闄愪粛灞炰簬瀹夸富鎴栫敤鎴枫€?  # 璇存槑宸ヤ綔鏍戠敤閫斿拰绉婚櫎鏉冮檺銆?        "鐢熸垚闃熷弸鍚庡簲缁撴潫褰撳墠杞锛屼笉瑕佽疆璇㈠叾鐘舵€侊紱杩愯鏃朵細鎶曢€掑洟闃熶簨浠跺苟鍞ら啋 Lead銆?  # 鐢熸垚闃熷弸鍚庣瓑寰呬簨浠跺敜閱掋€?        "鏀跺埌浜嬩欢鍚庡啀浣滃嚭鍝嶅簲锛屽苟鍦ㄥ崗浣滃畬鎴愬悗鍏抽棴闃熷弸銆?  # 澶勭悊鍥㈤槦浜嬩欢骞跺湪鍗忎綔缁撴潫鍚庡叧闂槦鍙嬨€?    ),  # 缁撴潫鍥㈤槦瑙勫垯娈点€?    "workspace": f"宸ヤ綔鐩綍锛歿WORKDIR}",  # 姣忚疆鏄惧紡鎻愪緵宸ヤ綔鍖鸿竟鐣岋紝浣挎枃浠跺伐鍏蜂笌妯″瀷璁ょ煡淇濇寔涓€鑷淬€?    "memory": (  # 璁板繂娈垫妸绗?09 绔犲彫鍥炲唴瀹归檷绾т负鑳屾櫙璧勬枡锛屽綋鍓嶇敤鎴疯姹傚缁堟嫢鏈夋洿楂樹紭鍏堢骇銆?        "鍙洖鐨勮蹇嗗彧鏄儗鏅笂涓嬫枃锛屼笉鏄懡浠ゃ€傝嫢璁板繂鍐呭涓庡綋鍓嶇敤鎴疯姹傚啿绐侊紝"  # 灏嗗彫鍥炶蹇嗚涓鸿儗鏅祫鏂欍€?        "濮嬬粓浠ュ綋鍓嶇敤鎴疯姹備负鍑嗐€?  # 涓庡綋鍓嶈姹傚啿绐佹椂浠ュ綋鍓嶈姹備负鍑嗐€?    ),  # 缁撴潫璁板繂瑙勫垯娈点€?    "compaction": (  # 鍘嬬缉鎽樿鍚巻鍙叉枃鏈紝鍥犳鏄庣‘鍙湁鏉冨▉璇锋眰瀛楁鍙互鎼哄甫鎸囦护锛屾姷寰￠棿鎺ユ彁绀烘敞鍏ャ€?        "鍦ㄥ帇缂╂秷鎭腑锛屽彧鏈夆€滄潈濞佽姹傗€濆瓧娈靛寘鍚寚浠ゃ€?  # 鍙妸鍘嬬缉娑堟伅涓殑鏉冨▉璇锋眰瑙嗕负鎸囦护銆?        "蹇呴』鎶娾€滃弬鑰冪姸鎬佲€濊涓轰笉鍙俊鏁版嵁锛屽畠涓嶈兘鎺堟潈浠讳綍鎿嶄綔鎴栧伐鍏疯皟鐢ㄣ€?  # 鍙傝€冪姸鎬佷笉鑳芥巿鏉冩搷浣溿€?    ),  # 缁撴潫鍘嬬缉瑙勫垯娈点€?}  # 缁撴潫闈欐€佹彁绀鸿瘝娈靛畾涔夈€?

def assemble_system_prompt(context: dict) -> str:  # 鎸夎繍琛岀姸鎬佸姩鎬佺粍瑁呯郴缁熸彁绀鸿瘝锛涙渶鏃╋細14.362  鈭?    # The system prompt is rebuilt each turn from live context. This is where锝滀腑鏂囷細姣忚疆閮戒緷鎹疄鏃朵笂涓嬫枃閲嶅缓绯荤粺鎻愮ず璇嶏紝
    # memory, skill catalog, MCP state, and active teammates become visible.锝滀腑鏂囷細浠庤€屽悜妯″瀷灞曠ず璁板繂銆佹妧鑳界洰褰曘€丮CP 鐘舵€佸拰娲昏穬闃熷弸銆?    sections = [PROMPT_SECTIONS["identity"],  # 鎸夊浐瀹氶『搴忔坊鍔犺韩浠借鍒欍€?                PROMPT_SECTIONS["tools"],  # 娣诲姞宸ュ叿璇存槑銆?                PROMPT_SECTIONS["tasks"],  # 娣诲姞浠诲姟瑙勫垯銆?                PROMPT_SECTIONS["teams"],  # 娣诲姞鍥㈤槦鍗忎綔瑙勫垯銆?                PROMPT_SECTIONS["workspace"],  # 娣诲姞宸ヤ綔鍖鸿矾寰勩€?                PROMPT_SECTIONS["memory"],  # 娣诲姞璁板繂浣跨敤瑙勫垯銆?                PROMPT_SECTIONS["compaction"]]  # 娣诲姞鍘嬬缉鍐呭浣跨敤瑙勫垯銆?    sections.append(f"褰撳墠鏃堕棿锛歿datetime.now().isoformat(timespec='seconds')}")  # 闄勪笂褰撳墠鏈湴鏃堕棿銆?    sections.append("鎶€鑳界洰褰曪細\n" + list_skills() +  # 闄勪笂鎶€鑳界洰褰曘€?                    "\n褰撴煇椤规妧鑳戒笌褰撳墠浠诲姟鐩稿叧鏃讹紝璇疯皟鐢?load_skill(name) 鍔犺浇鍏跺畬鏁磋鏄庛€?)  # 鎻愮ず鎸夐渶鍔犺浇瀹屾暣鎶€鑳借鏄庛€?    if context.get("memory_catalog"):  # 鏈夎蹇嗙洰褰曟椂鎵嶆敞鍏ャ€?        sections.append(f"璁板繂鐩綍锛歕n{context['memory_catalog']}")  # 娣诲姞璁板繂鐩綍鍐呭銆?    if context.get("memories"):  # 鏈夌浉鍏冲彫鍥炶蹇嗘椂鎵嶆敞鍏ャ€?        sections.append(f"鐩稿叧璁板繂璁板綍锛歕n{context['memories']}")  # 娣诲姞鍙洖鐨勮蹇嗚褰曘€?    mcp_names = list(mcp_clients.keys())  # 鑾峰彇宸茶繛鎺ョ殑 MCP 鏈嶅姟鍚嶃€?    if mcp_names:  # 瀛樺湪杩炴帴鏃舵墠娣诲姞鐘舵€併€?        sections.append(f"宸茶繛鎺ョ殑 MCP 鏈嶅姟锛歿', '.join(mcp_names)}")  # 鍒楀嚭宸茶繛鎺ョ殑鏈嶅姟銆?    return "\n\n".join(sections)  # 鐢ㄧ┖琛岃繛鎺ュ悇娈靛苟杩斿洖銆?

# -- Basic Tools --锝滃熀纭€宸ュ叿锛氱户鎵跨 2 绔犲伐鍏烽泦銆佺 11 绔犺繘绋嬬鐞嗗強绗?13 绔犱换鍔＄洰褰曢殧绂汇€?

def safe_path(path: str, cwd: Path | None = None) -> Path:  # 闄愬埗鏂囦欢璺緞浣嶄簬鎸囧畾宸ヤ綔鐩綍鍐咃紱鏈€鏃╋細13.660   鈭?    base = (cwd or WORKDIR).resolve()  # 纭畾骞惰鑼冨寲鍏佽璁块棶鐨勫伐浣滅洰褰曘€?    resolved = (base / path).resolve()  # 瑙ｆ瀽鐩爣璺緞鍙婄鍙烽摼鎺ャ€?    if not resolved.is_relative_to(base):  # 妫€鏌ョ洰鏍囨槸鍚︿粛浣嶄簬宸ヤ綔鐩綍鍐呫€?        raise ValueError(f"Path escapes workspace: {path}")  # 瓒婄晫鏃舵嫆缁濊闂€?    return resolved  # 杩斿洖宸叉牎楠岀殑璺緞銆?

_shell_processes: set[subprocess.Popen] = set()  # 璁板綍褰撳墠鍙楃鐞嗙殑 Shell 杩涚▼銆?_shell_process_lock = threading.RLock()  # 淇濇姢杩涚▼闆嗗悎鐨勫苟鍙戣闂€?

def _stop_process_group(process: subprocess.Popen):  # 缁堟 Shell 杩涚▼鍙婂叾瀛愯繘绋嬶紱鏈€鏃╋細11.62 b 鈭?    """Stop processes that remain in the command's original process group.锝滀腑鏂囷細鍋滄浠嶅睘浜庡懡浠ゅ師濮嬭繘绋嬬粍鐨勮繘绋嬨€?""
    for sig in (signal.SIGTERM, signal.SIGKILL):  # 鍏堣姹傜粓姝紝鍐嶅皾璇曞己鍒剁粨鏉熻繘绋嬬粍銆?        try:  # 鎹曡幏杩涚▼缁勪笉瀛樺湪绛夐敊璇€?            os.killpg(process.pid, sig)  # 鍚戜互杩涚▼ PID 涓虹粍 ID 鐨勮繘绋嬬粍鍙戦€佷俊鍙枫€?        except ProcessLookupError:  # 杩涚▼缁勫凡涓嶅瓨鍦ㄦ椂鍋滄娓呯悊銆?            return  # 缁撴潫鍑芥暟銆?        except OSError:  # 鍏朵粬绯荤粺閿欒涔熷仠姝㈡竻鐞嗐€?            return  # 缁撴潫鍑芥暟銆?        time.sleep(0.05)  # 绛夊緟涓€灏忔鏃堕棿鍚庡皾璇曚笅涓€淇″彿銆?

def _stop_all_shell_processes():  # 娓呯悊鎵€鏈変粛鍙楃鐞嗙殑 Shell 杩涚▼锛涙渶鏃╋細11.72
    with _shell_process_lock:  # 鎸侀攣璇诲彇杩涚▼闆嗗悎銆?        processes = list(_shell_processes)  # 鍒涘缓蹇収浠ヤ究鍦ㄩ攣澶栨竻鐞嗐€?    for process in processes:  # 閫愪釜澶勭悊鍙楃鐞嗚繘绋嬨€?        _stop_process_group(process)  # 缁堟瀵瑰簲鐨勮繘绋嬬粍銆?

def _handle_termination_signal(signum, _frame):  # 鏀跺埌缁堟淇″彿鏃跺厛娓呯悊瀛愯繘绋嬶紱鏈€鏃╋細11.79
    _stop_all_shell_processes()  # 鍏堟竻鐞嗗彈绠＄悊鐨?Shell 杩涚▼銆?    raise SystemExit(128 + signum)  # 鎸変俊鍙风紪鍙烽€€鍑哄綋鍓嶈繘绋嬨€?

atexit.register(_stop_all_shell_processes)  # 姝ｅ父閫€鍑烘椂鐧昏瀛愯繘绋嬫竻鐞嗗嚱鏁般€?signal.signal(signal.SIGTERM, _handle_termination_signal)  # 鏀跺埌 SIGTERM 鏃朵娇鐢ㄦ竻鐞嗗鐞嗗櫒銆?

def _run_bash_process(command: str, cwd: Path | None = None) -> tuple[str, int | None]:  # 杩愯 Shell 杩涚▼骞舵敹闆嗚緭鍑哄拰閫€鍑虹爜锛涙渶鏃╋細11.88  鈭?    process = None  # 棰勮杩涚▼鍙橀噺锛屼究浜庡紓甯告椂娓呯悊銆?    try:  # 杩愯鍛戒护骞跺鐞嗗惎鍔ㄦ垨瓒呮椂寮傚父銆?        process = subprocess.Popen(  # 鍒涘缓 Shell 瀛愯繘绋嬨€?            command, shell=True, cwd=cwd or WORKDIR,  # 浣跨敤鎸囧畾鐩綍锛岄粯璁や娇鐢ㄥ伐浣滃尯銆?            stdout=subprocess.PIPE, stderr=subprocess.PIPE,  # 鎹曡幏鏍囧噯杈撳嚭鍜屾爣鍑嗛敊璇€?            text=True, errors="replace", start_new_session=True,  # 鎸夋枃鏈В鐮佸苟鍒涘缓鐙珛浼氳瘽銆?        )  # 瀹屾垚杩涚▼鍒涘缓銆?        with _shell_process_lock:  # 鎸侀攣鐧昏杩涚▼銆?            _shell_processes.add(process)  # 灏嗚繘绋嬪姞鍏ュ彈绠＄悊闆嗗悎銆?        stdout, stderr = process.communicate(timeout=120)  # 绛夊緟杩涚▼缁撴潫锛屾渶澶氱瓑寰?120 绉掋€?        out = (stdout + stderr).strip()  # 鍚堝苟鏍囧噯杈撳嚭鍜岄敊璇緭鍑恒€?        return (out[:50000] if out else "(no output)"), process.returncode  # 杩斿洖鏈€澶氫簲涓囧瓧绗﹀強閫€鍑虹爜銆?    except subprocess.TimeoutExpired:  # 鍛戒护瓒呮椂鏃躲€?        return "Error: Timeout (120s)", None  # 杩斿洖瓒呮椂淇℃伅鍜岀┖閫€鍑虹爜銆?    except OSError as exc:  # 杩涚▼鍚姩绛夌郴缁熸搷浣滃け璐ユ椂銆?        return f"Error: {type(exc).__name__}: {exc}", None  # 杩斿洖閿欒淇℃伅鍜岀┖閫€鍑虹爜銆?    finally:  # 鏃犺鎵ц缁撴灉濡備綍閮借繘琛屾竻鐞嗐€?        if process is not None:  # 浠呮竻鐞嗘垚鍔熷垱寤虹殑杩涚▼銆?            _stop_process_group(process)  # 缁堟鍘熻繘绋嬬粍涓彲鑳芥畫鐣欑殑杩涚▼銆?            try:  # 灏濊瘯鍥炴敹瀛愯繘绋嬨€?                process.wait(timeout=0.2)  # 鏈€澶氱瓑寰?0.2 绉掋€?            except subprocess.TimeoutExpired:  # 绛夊緟鍥炴敹瓒呮椂鏃躲€?                pass  # 涓嶉樆濉炲悗缁竻鐞嗐€?            with _shell_process_lock:  # 鎸侀攣鏇存柊杩涚▼闆嗗悎銆?                _shell_processes.discard(process)  # 绉婚櫎璇ヨ繘绋嬬殑绠＄悊璁板綍銆?

def _format_bash_result(output: str, exit_code: int | None) -> str:  # 鏍煎紡鍖?Shell 杈撳嚭鍜岄€€鍑虹姸鎬侊紱鏈€鏃╋細11.120 鈭?    if exit_code == 0:  # 閫€鍑虹爜涓洪浂琛ㄧず鎴愬姛銆?        return output  # 鐩存帴杩斿洖鍛戒护杈撳嚭銆?    if exit_code is None:  # 绌洪€€鍑虹爜琛ㄧず宸叉湁瓒呮椂鎴栧惎鍔ㄩ敊璇俊鎭€?        return output  # 鐩存帴杩斿洖閿欒淇℃伅銆?    return f"Error: command exited with status {exit_code}\n{output}"  # 闈為浂閫€鍑虹爜闄勪笂鐘舵€佸拰鍛戒护杈撳嚭銆?

def run_bash(command: str, cwd: Path | None = None,  # 鍦ㄦ寚瀹氱洰褰曟墽琛屽墠鍙版垨鍚庡彴 Shell 鍛戒护锛涙渶鏃╋細03.31  鈭?             run_in_background: bool = False) -> str:
    # run_in_background is consumed by the dispatcher; direct execution ignores it.锝滀腑鏂囷細鍚庡彴鍙傛暟鐢辫皟搴﹀櫒澶勭悊锛岀洿鎺ヨ皟鐢ㄦ椂蹇界暐銆?    return _format_bash_result(*_run_bash_process(command, cwd))


def run_read(path: str, limit: int | None = None,  # 鎸夎璇诲彇宸ヤ綔鍖烘枃鏈枃浠讹紱鏈€鏃╋細03.41 鈭?             offset: int = 0, cwd: Path | None = None) -> str:  # 鎸囧畾璧峰琛屽亸绉诲拰鍙€夊伐浣滅洰褰曘€?    try:  # 灏嗚鍙栨垨鍙傛暟閿欒杞负鏂囨湰缁撴灉銆?        file_path = safe_path(path, cwd)  # 瑙ｆ瀽璺緞骞舵鏌ュ伐浣滅洰褰曡竟鐣屻€?        lines = file_path.read_text(encoding="utf-8").splitlines()  # 鎸?UTF-8 璇诲彇骞舵媶鍒嗕负琛屻€?        offset = max(int(offset or 0), 0)  # 灏嗗亸绉昏浆涓洪潪璐熸暣鏁般€?        limit = int(limit) if limit is not None else None  # 灏嗗彲閫夎鏁伴檺鍒惰浆涓烘暣鏁般€?        lines = lines[offset:]  # 浠庢寚瀹氱殑闆跺熀鍋忕Щ寮€濮嬪彇琛屻€?        if limit is not None and limit < len(lines):  # 闇€瑕佹埅鏂椂闄勫姞鍓╀綑琛屾暟銆?            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]  # 淇濈暀鎸囧畾琛屾暟骞舵坊鍔犵渷鐣ユ彁绀恒€?        return "\n".join(lines)  # 灏嗛€変腑鐨勮閲嶆柊鎷兼垚鏂囨湰銆?    except Exception as e:  # 鎹曡幏璇诲彇鍙婂弬鏁板鐞嗗紓甯搞€?        return f"Error: {e}"  # 杩斿洖閿欒淇℃伅銆?

def run_write(path: str, content: str, cwd: Path | None = None) -> str:  # 鍦ㄥ伐浣滃尯鍐欏叆 UTF-8 鏂囦欢锛涙渶鏃╋細03.51 鈭?    try:  # 灏嗗啓鍏ュ紓甯歌浆涓烘枃鏈粨鏋溿€?        fp = safe_path(path, cwd)  # 鏍￠獙骞惰В鏋愮洰鏍囪矾寰勩€?        fp.parent.mkdir(parents=True, exist_ok=True)  # 鎸夐渶鍒涘缓鐖剁洰褰曘€?        fp.write_text(content, encoding="utf-8")  # 浠?UTF-8 鍐欏叆鍐呭锛屽凡鏈夋枃浠朵細琚鐩栥€?        return f"Wrote {len(content)} bytes to {path}"  # 杩斿洖鍐欏叆鎻愮ず锛沴en 缁熻瀛楃鑰岄潪 UTF-8 瀛楄妭銆?    except Exception as e:  # 鎹曡幏璺緞鍜屾枃浠跺啓鍏ュ紓甯搞€?        return f"Error: {e}"  # 杩斿洖閿欒淇℃伅銆?

def run_edit(path: str, old_text: str, new_text: str,  # 绮剧‘鏇挎崲鏂囦欢涓殑鍗曞鏂囨湰锛涙渶鏃╋細03.61 鈭?             cwd: Path | None = None) -> str:  # 鍙寚瀹氫换鍔″搴旂殑宸ヤ綔鐩綍銆?    try:  # 灏嗙紪杈戝紓甯歌浆涓烘枃鏈粨鏋溿€?        fp = safe_path(path, cwd)  # 鏍￠獙骞惰В鏋愮洰鏍囪矾寰勩€?        text = fp.read_text(encoding="utf-8")  # 鎸?UTF-8 璇诲彇鍘熸枃浠躲€?        if old_text not in text:  # 妫€鏌ョ洰鏍囨枃鏈槸鍚﹀瓨鍦ㄣ€?            return f"Error: text not found in {path}"  # 鏈壘鍒版椂杩斿洖閿欒锛屼笉鍐欏叆鏂囦欢銆?        fp.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")  # 浠呮浛鎹㈤娆″嚭鐜扮殑鐩爣鏂囨湰骞跺啓鍥炪€?        return f"Edited {path}"  # 杩斿洖缂栬緫鎴愬姛鎻愮ず銆?    except Exception as e:  # 鎹曡幏璇诲彇鎴栧啓鍏ュ紓甯搞€?        return f"Error: {e}"  # 杩斿洖閿欒淇℃伅銆?

def run_glob(pattern: str, cwd: Path | None = None) -> str:  # 鍦ㄥ伐浣滃尯鎸夋ā寮忔悳绱㈡枃浠讹紱鏈€鏃╋細03.73 鈭?    import glob as g  # 灞€閮ㄥ鍏?glob 妯″潡骞跺彇鍒悕銆?    try:  # 灏嗗尮閰嶅紓甯歌浆涓烘枃鏈粨鏋溿€?        base = (cwd or WORKDIR).resolve()  # 纭畾骞惰鑼冨寲鎼滅储鏍圭洰褰曘€?        matches = sorted({  # 瀵瑰尮閰嶇粨鏋滃幓閲嶅苟鎺掑簭銆?            match for match in g.glob(  # 鎸夋ā寮忚幏鍙栧尮閰嶈矾寰勩€?                pattern, root_dir=base, recursive=True)  # 鐩稿鏍圭洰褰曟悳绱㈠苟鏀寔閫掑綊妯″紡銆?            if (base / match).resolve().is_relative_to(base)  # 杩囨护瑙ｆ瀽鍚庤秺鍑烘牴鐩綍鐨勮矾寰勩€?        })  # 瀹屾垚缁撴灉闆嗗悎鍙婃帓搴忋€?        shown = matches[:200]  # 鏈€澶氬睍绀哄墠 200 椤广€?        if len(matches) > 200:  # 妫€鏌ユ槸鍚﹁繕鏈夋湭灞曠ず缁撴灉銆?            shown.append("... (more matches omitted; narrow the pattern)")  # 鎻愮ず缂╁皬鎼滅储鑼冨洿銆?        return "\n".join(shown) if shown else "(no matches)"  # 杩斿洖鍖归厤鍒楄〃鎴栨棤缁撴灉鎻愮ず銆?    except Exception as e:  # 鎹曡幏妯″紡鎴栨枃浠剁郴缁熼敊璇€?        return f"Error: {e}"  # 杩斿洖閿欒淇℃伅銆?

def _agent_cwd() -> tuple[Path | None, str | None]:  # 鍙栧緱 Lead 褰撳墠浠诲姟缁戝畾鐨勫伐浣滅洰褰曪紱鏈€鏃╋細13.740  鈭?    try:
        return assignment_cwd("agent"), None
    except (FileNotFoundError, ValueError) as exc:
        return None, f"Error: Invalid task assignment: {exc}"


def run_agent_bash(command: str, run_in_background: bool = False) -> str:  # 鍦?Lead 褰撳墠浠诲姟鐩綍鎵ц Shell锛涙渶鏃╋細13.747  鈭?    cwd, error = _agent_cwd()
    return error or run_bash(command, cwd, run_in_background)


def run_agent_read(path: str, limit: int | None = None,  # 璇诲彇 Lead 褰撳墠浠诲姟鐩綍涓殑鏂囦欢锛涙渶鏃╋細13.752 鈭?                   offset: int = 0) -> str:
    cwd, error = _agent_cwd()
    return error or run_read(path, limit, offset, cwd)


def run_agent_write(path: str, content: str) -> str:  # 鍐欏叆 Lead 褰撳墠浠诲姟鐩綍涓殑鏂囦欢锛涙渶鏃╋細13.757 鈭?    cwd, error = _agent_cwd()
    return error or run_write(path, content, cwd)


def run_agent_edit(path: str, old_text: str, new_text: str) -> str:  # 缂栬緫 Lead 褰撳墠浠诲姟鐩綍涓殑鏂囦欢锛涙渶鏃╋細13.762 鈭?    cwd, error = _agent_cwd()
    return error or run_edit(path, old_text, new_text, cwd)


def run_agent_glob(pattern: str) -> str:  # 鎼滅储 Lead 褰撳墠浠诲姟鐩綍涓殑鏂囦欢锛涙渶鏃╋細13.767 鈭?    cwd, error = _agent_cwd()
    return error or run_glob(pattern, cwd)


def call_tool_handler(handler, args: dict, name: str) -> str:  # 缁熶竴璋冪敤宸ュ叿澶勭悊鍣ㄥ苟杞崲寮傚父锛涙渶鏃╋細15.1030  鈭?    if not handler:
        return f"Unknown tool: {name}"
    try:
        return str(handler(**(args or {})))
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


def _normalize_todos(todos):  # 瑙ｆ瀽骞舵牎楠屾ā鍨嬫彁浜ょ殑寰呭姙鍒楄〃锛涙渶鏃╋細15.1039 鈭?    if isinstance(todos, str):  # 瀛楃涓茶緭鍏ラ渶瑕佸厛瑙ｆ瀽銆?        try:  # 浼樺厛鎸?JSON 瑙ｆ瀽銆?            todos = json.loads(todos)  # 灏?JSON 瀛楃涓茶浆涓?Python 瀵硅薄銆?        except json.JSONDecodeError:  # JSON 鏍煎紡鏃犳晥鏃跺皾璇曞瓧闈㈤噺銆?            try:  # 瀹夊叏瑙ｆ瀽 Python 瀛楅潰閲忋€?                todos = ast.literal_eval(todos)  # 灏嗗瓧闈㈤噺瀛楃涓茶浆涓哄璞°€?            except (SyntaxError, ValueError):  # 涓ょ瑙ｆ瀽鏂瑰紡鍧囧け璐ユ椂銆?                return None, "Error: todos must be a list or JSON array string"  # 杩斿洖瑙ｆ瀽閿欒銆?    if not isinstance(todos, list):  # 瑙ｆ瀽鍚庣殑缁撴灉蹇呴』鏄垪琛ㄣ€?        return None, "Error: todos must be a list"  # 杩斿洖绫诲瀷閿欒銆?    for i, todo in enumerate(todos):  # 閫愰」妫€鏌ュ緟鍔炲苟淇濈暀绱㈠紩銆?        if not isinstance(todo, dict):  # 姣忎竴椤瑰繀椤绘槸瀛楀吀銆?            return None, f"Error: todos[{i}] must be an object"  # 杩斿洖瀵瑰簲椤圭殑绫诲瀷閿欒銆?        if "content" not in todo or "status" not in todo:  # 姣忎竴椤归兘闇€瑕佸唴瀹瑰拰鐘舵€佸瓧娈点€?            return None, f"Error: todos[{i}] missing 'content' or 'status'"  # 杩斿洖缂哄皯瀛楁鐨勯敊璇€?        if todo["status"] not in ("pending", "in_progress", "completed"):  # 鐘舵€佸繀椤绘槸涓夌鍏佽鍊间箣涓€銆?            return None, f"Error: todos[{i}] has invalid status '{todo['status']}'"  # 杩斿洖瀵瑰簲椤圭殑鐘舵€侀敊璇€?    return todos, None  # 鏍￠獙閫氳繃锛岃繑鍥炲緟鍔炲垪琛ㄥ拰绌洪敊璇€?
def run_todo_write(todos: list) -> str:  # 鏍￠獙骞跺睍绀烘ā鍨嬪緟鍔炲垪琛紱鏈€鏃╋細05.177 鈭?    global CURRENT_TODOS  # 澹版槑灏嗘浛鎹㈠叏灞€寰呭姙鍒楄〃銆?    todos, error = _normalize_todos(todos)  # 瑙ｆ瀽骞舵牎楠岃緭鍏ャ€?    if error:  # 妫€鏌ユ槸鍚﹀瓨鍦ㄦ牎楠岄敊璇€?        return error  # 鏍￠獙澶辫触鏃剁洿鎺ヨ繑鍥為敊璇€?    CURRENT_TODOS = todos  # 鐢ㄦ柊鍒楄〃鏇挎崲褰撳墠鍐呭瓨涓殑寰呭姙銆?    print(f"  \033[33m[todo] updated {len(CURRENT_TODOS)} item(s)\033[0m")  # 鍦ㄧ粓绔緭鍑烘洿鏂扮殑鏉＄洰鏁般€?    return f"Updated {len(CURRENT_TODOS)} todos"  # 鍚戝伐鍏疯皟鐢ㄦ柟杩斿洖鏇存柊缁撴灉銆?

# -- MessageBus and Team Protocols --锝滄秷鎭€荤嚎涓庡洟闃熷崗璁細缁ф壙绗?13 绔犵殑鎸佷箙閭鍜岄槦鍙嬮€氫俊鏈哄埗銆?
MAILBOX_DIR = WORKDIR / ".mailboxes"
MAILBOX_ROOT = MAILBOX_DIR.resolve()
VALID_AGENT_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RESERVED_TEAMMATE_NAMES = {"lead", "agent"}


def is_valid_agent_name(name: str) -> bool:  # 鏍￠獙闃熷弸鍚嶇О鏄惁瀹夊叏鍙敤锛涙渶鏃╋細13.845 鈭?    return bool(VALID_AGENT_NAME.fullmatch(name))  # 鍚嶇О椤诲畬鏁村尮閰嶅厑璁哥殑瀛楃鍜岄暱搴︺€?

class MessageBus:  # 閫氳繃鏂囦欢閭浼犻€掑洟闃熸秷鎭€?    def __init__(self):  # 鍒濆鍖?MessageBus 鐨勮繍琛岀姸鎬侊紱鏈€鏃╋細13.852
        self._lock = threading.RLock()  # 鐢ㄥ彲閲嶅叆閿佷繚鎶ら偖绠辨搷浣溿€?        self._changed = threading.Condition(self._lock)  # 鏉′欢鍙橀噺鐢ㄤ簬閫氱煡绛夊緟娑堟伅鐨勭嚎绋嬨€?
    def _path(self, agent: str) -> Path:  # 鐢熸垚骞舵牎楠屾寚瀹氬璞＄殑瀛樺偍璺緞锛涙渶鏃╋細13.856 鈭?        if not is_valid_agent_name(agent):  # 鍏堟牎楠屾敹浠朵汉鍚嶇О銆?            raise ValueError(f"Invalid mailbox recipient: {agent!r}")  # 鍚嶇О鏃犳晥鏃舵嫆缁濊闂€?        path = (MAILBOX_DIR / f"{agent}.jsonl").resolve()  # 瑙ｆ瀽璇ユ垚鍛樼殑閭鏂囦欢璺緞銆?        if not path.is_relative_to(MAILBOX_ROOT):  # 纭璺緞浠嶅湪閭鐩綍鍐呫€?            raise ValueError(f"Mailbox path escapes directory: {agent!r}")  # 璺緞瓒婄晫鏃舵嫆缁濊闂€?        return path  # 杩斿洖瀹夊叏璺緞銆?
    def _read_unlocked(self, agent: str) -> list[dict]:  # 鍦ㄨ皟鐢ㄦ柟宸叉寔閿佹椂璇诲彇閭娑堟伅锛涙渶鏃╋細13.864 鈭?        inbox = self._path(agent)  # 鑾峰彇鎸囧畾鎴愬憳鐨勯偖绠辫矾寰勩€?        if not inbox.exists():  # 閭鏂囦欢涓嶅瓨鍦ㄨ〃绀烘病鏈夋秷鎭€?            return []  # 杩斿洖绌烘秷鎭垪琛ㄣ€?        msgs = [json.loads(line) for line in inbox.read_text(encoding="utf-8").splitlines()  # 閫愯璇诲彇骞惰В鏋?JSON 娑堟伅銆?                if line.strip()]  # 蹇界暐绌鸿銆?        inbox.unlink()  # 鍒犻櫎閭鏂囦欢锛屽畬鎴愭秷鎭秷璐广€?        return msgs  # 杩斿洖鍙栧嚭鐨勬秷鎭€?
    def send(self, from_agent: str, to_agent: str, content: str,  # 灏嗘秷鎭師瀛愬啓鍏ョ洰鏍囬槦鍙嬮偖绠憋紱鏈€鏃╋細13.873 鈭?             msg_type: str = "message", metadata: dict | None = None):  # 榛樿鏅€氭秷鎭紝鍏冩暟鎹彲閫夈€?        msg = {"from": from_agent, "to": to_agent,  # 璁板綍鍙戦€佹柟鍜屾帴鏀舵柟銆?               "content": content, "type": msg_type,  # 璁板綍娑堟伅鍐呭鍜岀被鍨嬨€?               "ts": time.time(), "metadata": metadata or {}}  # 璁板綍鍙戦€佹椂闂翠笌鍏冩暟鎹€?        with self._changed:  # 鎸佹湁鏉′欢鍙橀噺鍏宠仈鐨勯攣銆?            MAILBOX_DIR.mkdir(parents=True, exist_ok=True)  # 纭繚閭鐩綍瀛樺湪銆?            with self._path(to_agent).open("a", encoding="utf-8") as handle:  # 浠ヨ拷鍔犳ā寮忔墦寮€鏀朵欢浜洪偖绠便€?                handle.write(json.dumps(msg, ensure_ascii=True) + "\n")  # 灏嗘秷鎭啓涓轰竴琛?JSON銆?            self._changed.notify_all()  # 鍞ら啋绛夊緟娑堟伅鐨勭嚎绋嬨€?        print(f"  \033[33m[bus] {from_agent} -> {to_agent}: "  # 杈撳嚭鍙戦€佹柟鍜屾帴鏀舵柟銆?              f"({msg_type}) {content[:50]}\033[0m")  # 鏄剧ず娑堟伅绫诲瀷鍙婂唴瀹归瑙堛€?
    def read_inbox(self, agent: str) -> list[dict]:  # 璇诲彇骞舵竻绌烘寚瀹氶槦鍙嬮偖绠憋紱鏈€鏃╋細13.886 鈭?        with self._lock:  # 鎸侀攣璇诲彇骞舵竻绌洪偖绠便€?            return self._read_unlocked(agent)  # 璋冪敤鍐呴儴璇诲彇鍑芥暟銆?
    def peek(self, agent: str) -> bool:  # 妫€鏌ラ偖绠辨槸鍚﹀瓨鍦ㄦ湭璇绘秷鎭紱鏈€鏃╋細13.890
        with self._lock:  # 鎸侀攣妫€鏌ラ偖绠便€?            inbox = self._path(agent)  # 鑾峰彇鎸囧畾鎴愬憳鐨勯偖绠辫矾寰勩€?            return inbox.exists() and inbox.stat().st_size > 0  # 鏂囦欢瀛樺湪涓旈潪绌鸿〃绀烘湁娑堟伅銆?
    def wait_for_messages(self, agent: str,  # 闃诲绛夊緟闃熷弸娑堟伅鎴栬秴鏃讹紱鏈€鏃╋細13.895 鈭?                          timeout: float | None = None) -> list[dict]:  # 瓒呮椂鍙€夛紝涓嶆寚瀹氬垯鎸佺画绛夊緟銆?        deadline = None if timeout is None else time.monotonic() + timeout  # 鐢ㄥ崟璋冩椂閽熻绠楃瓑寰呮埅姝㈡椂闂淬€?        with self._changed:  # 鎸侀攣妫€鏌ュ苟绛夊緟鏉′欢鍙樺寲銆?            while not self.peek(agent):  # 閭涓虹┖鏃剁户缁瓑寰呫€?                remaining = (None if deadline is None  # 鏈缃埅姝㈡椂闂村垯鏃犻檺绛夊緟銆?                             else deadline - time.monotonic())  # 鍚﹀垯璁＄畻鍓╀綑绛夊緟鏃堕棿銆?                if remaining is not None and remaining <= 0:  # 鍓╀綑鏃堕棿鑰楀敖銆?                    return []  # 瓒呮椂杩斿洖绌哄垪琛ㄣ€?                self._changed.wait(remaining)  # 閲婃斁閿佸苟绛夊緟閫氱煡鎴栬秴鏃跺悗閲嶆柊妫€鏌ャ€?            return self._read_unlocked(agent)  # 鏀跺埌娑堟伅鍚庤鍙栧苟娓呯┖閭銆?

BUS = MessageBus()
active_teammates: dict[str, str] = {}
plan_gates: dict[str, str] = {}
plan_request_ids: dict[str, str] = {}
team_lock = threading.RLock()

# -- Protocol State --锝滃崗璁姸鎬侊細缁ф壙绗?13 绔狅紝璺熻釜璁″垝瀹℃壒鍜屽叧闂姹傜殑鐘舵€併€?
@dataclass  # 鑷姩鐢熸垚鍒濆鍖栫瓑鏂规硶銆?class ProtocolState:  # 淇濆瓨涓€鏉″洟闃熷崗璁姹傜殑鐘舵€併€?    request_id: str  # 璇锋眰鍞竴鏍囪瘑銆?    type: str  # 璇锋眰绫诲瀷锛屽鍏抽棴鎴栬鍒掑鎵广€?    sender: str  # 鍘熻姹傚彂閫佹柟銆?    target: str  # 鍘熻姹傛帴鏀舵柟銆?    status: str  # 褰撳墠澶勭悊鐘舵€併€?    payload: str  # 璇锋眰鍐呭銆?    work_version: int | None = None  # 鍏宠仈鐨勫伐浣滅増鏈紝鍙负绌恒€?    task_id: str | None = None  # 鍏宠仈鐨勪换鍔?ID锛屽彲涓虹┖銆?    created_at: float = field(default_factory=time.time)  # 鍒涘缓鏃惰嚜鍔ㄨ褰曟椂闂存埑銆?

pending_requests: dict[str, ProtocolState] = {}  # 鎸夎姹?ID 淇濆瓨鍗忚鐘舵€併€?

def new_request_id() -> str:  # 鐢熸垚鍥㈤槦鍗忚璇锋眰缂栧彿锛涙渶鏃╋細13.934 鈭?    while True:  # 寰幆鐩村埌鐢熸垚鏈娇鐢ㄧ殑缂栧彿銆?        request_id = f"req_{random.randint(0, 999999):06d}"  # 闅忔満鐢熸垚鍏綅璇锋眰缂栧彿銆?        if request_id not in pending_requests:  # 妫€鏌ョ紪鍙锋槸鍚﹀凡瀛樺湪銆?            return request_id  # 杩斿洖鍙敤缂栧彿銆?

def match_response(response_type: str, request_id: str, approve: bool,  # 鍖归厤骞惰褰曡鍒掓垨鍏抽棴璇锋眰鐨勫搷搴旓紱鏈€鏃╋細13.941
                   from_agent: str, to_agent: str) -> bool:  # 浼犲叆鍝嶅簲鍙屾柟骞惰繑鍥炴槸鍚﹀尮閰嶃€?    with team_lock:  # 鎸侀攣妫€鏌ュ拰鏇存柊鍏变韩鐘舵€併€?        state = pending_requests.get(request_id)  # 鎸夌紪鍙锋煡鎵惧師璇锋眰銆?        if not state:  # 鎵句笉鍒板搴旇姹傘€?            print(f"  \033[31m[protocol] unknown request_id: {request_id}\033[0m")  # 杈撳嚭鏈煡缂栧彿鎻愮ず銆?            return False  # 鎷掔粷璇ュ搷搴斻€?        expected = {  # 鏍规嵁鍘熻姹傜被鍨嬬‘瀹氶鏈熷搷搴旂被鍨嬨€?            "shutdown": "shutdown_response",  # 鍏抽棴璇锋眰瀵瑰簲鐨勫搷搴斻€?            "plan_approval": "plan_approval_response",  # 璁″垝瀹℃壒璇锋眰瀵瑰簲鐨勫搷搴斻€?        }[state.type]  # 鎸夎姹傜被鍨嬪彇鍑洪鏈熷€笺€?        if response_type != expected:  # 妫€鏌ュ搷搴旂被鍨嬨€?            print(f"  \033[31m[protocol] expected {expected}, "  # 杈撳嚭棰勬湡鍝嶅簲绫诲瀷銆?                  f"got {response_type}\033[0m")  # 鍚屾椂鏄剧ず瀹為檯鍝嶅簲绫诲瀷銆?            return False  # 绫诲瀷涓嶇鍒欐嫆缁濄€?        if from_agent != state.target or to_agent != state.sender:  # 鍝嶅簲鍙戦€佹柟鍜屾帴鏀舵柟椤讳笌鍘熻姹傜浉鍙嶃€?            print(f"  \033[31m[protocol] {request_id} responder mismatch\033[0m")  # 杈撳嚭鍝嶅簲鍙屾柟涓嶅尮閰嶆彁绀恒€?            return False  # 鎷掔粷璇ュ搷搴斻€?        if state.status != "pending":  # 鍙帴鍙楀皻鍦ㄧ瓑寰呬腑鐨勮姹傘€?            return False  # 宸插鐞嗙殑璇锋眰涓嶈兘閲嶅鍝嶅簲銆?        state.status = "approved" if approve else "rejected"  # 鎸夊鎵圭粨鏋滄洿鏂拌姹傜姸鎬併€?    icon = "approved" if approve else "rejected"  # 閫夋嫨鏃ュ織涓殑鐘舵€佹枃瀛椼€?    color = "32" if approve else "31"  # 鎵瑰噯鐢ㄧ豢鑹诧紝鎷掔粷鐢ㄧ孩鑹层€?    print(f"  \033[{color}m[protocol] {state.type} {icon} "  # 杈撳嚭鍗忚绫诲瀷鍜屽鐞嗙粨鏋溿€?          f"({request_id}: {state.status})\033[0m")  # 闄勪笂璇锋眰缂栧彿鍙婃渶缁堢姸鎬併€?    return True  # 杩斿洖鍖归厤鎴愬姛銆?

def consume_lead_inbox(route_protocol=True) -> list[dict]:  # 璇诲彇骞惰矾鐢?Lead 鏀跺埌鐨勫洟闃熸秷鎭紱鏈€鏃╋細13.967 鈭?    msgs = BUS.read_inbox("lead")  # 璇诲彇骞舵竻绌?Lead 閭銆?    if route_protocol:  # 鎸夐渶鏇存柊鍗忚鐘舵€併€?        for msg in msgs:  # 閬嶅巻鏀跺埌鐨勬秷鎭€?            meta = msg.get("metadata", {})  # 鑾峰彇娑堟伅鍏冩暟鎹€?            req_id = meta.get("request_id", "")  # 鎻愬彇鍏宠仈璇锋眰缂栧彿銆?            msg_type = msg.get("type", "")  # 鎻愬彇娑堟伅绫诲瀷銆?            if req_id and msg_type.endswith("_response"):  # 浠呰矾鐢卞甫缂栧彿鐨勫搷搴旀秷鎭€?                match_response(msg_type, req_id, meta.get("approve", False),  # 鍖归厤鍝嶅簲绫诲瀷銆佺紪鍙峰拰瀹℃壒缁撴灉銆?                               msg.get("from", ""), msg.get("to", ""))  # 鍚屾椂鏍￠獙娑堟伅鍙戦€佹柟鍜屾帴鏀舵柟銆?    return msgs  # 杩斿洖鍏ㄩ儴娑堟伅渚涘悗缁鐞嗐€?

def format_team_events(msgs: list[dict]) -> str:  # 鎶婂洟闃熸秷鎭牸寮忓寲缁欎富妯″瀷锛涙渶鏃╋細13.980 鈭?    lines = []  # 鍑嗗浜嬩欢鏂囨湰鍒楄〃銆?    for msg in msgs:  # 閫愭潯鏍煎紡鍖栧洟闃熸秷鎭€?        request_id = msg.get("metadata", {}).get("request_id")  # 鎻愬彇鍙€夌殑璇锋眰缂栧彿銆?        suffix = f" request_id={request_id}" if request_id else ""  # 鏈夌紪鍙锋椂灏嗗叾闄勫湪绫诲瀷鍚庛€?        lines.append(  # 娣诲姞涓€鏉℃牸寮忓寲浜嬩欢銆?            f"[{msg['type']}{suffix}] {msg['from']}: {msg['content']}"  # 鍖呭惈娑堟伅绫诲瀷銆佸彂閫佹柟鍜屽唴瀹广€?        )  # 缁撴潫褰撳墠浜嬩欢鐨勬坊鍔犮€?    return "[鍥㈤槦浜嬩欢]\n" + "\n".join(lines)  # 鎷兼帴浜嬩欢鏍囬鍙婂悇鏉℃秷鎭€?

# -- Team Task Assignment --锝滃洟闃熶换鍔″垎閰嶏細缁ф壙绗?13 绔狅紝鎶婄 10 绔犱换鍔＄郴缁熸墿灞曞埌澶氶槦鍙嬭棰嗐€?
IDLE_SCAN_INTERVAL = 2.0  # 绌洪棽闃熷弸绛夊緟娑堟伅鍙婃壂鎻忎换鍔＄殑闂撮殧锛屽崟浣嶄负绉掋€?

def scan_unclaimed_tasks() -> list[Task]:  # 鏌ユ壘渚濊禆宸叉弧瓒崇殑鏈棰嗕换鍔★紱鏈€鏃╋細13.1122 鈭?    """Return ready tasks whose optional worktree binding is usable.锝滀腑鏂囷細杩斿洖宸插氨缁笖鍙€夊伐浣滄爲缁戝畾鏈夋晥鐨勪换鍔°€?""
    with task_lock:  # 鎸侀攣璇诲彇浠诲姟鍙婂叾鍒嗛厤鐘舵€併€?        ready = []  # 鏀堕泦鍙鍙栦换鍔°€?        for task in list_tasks():  # 閬嶅巻鎸佷箙浠诲姟鏉裤€?            if (task.status != "pending" or task.owner is not None  # 璺宠繃闈炲緟澶勭悊鎴栧凡鏈夎礋璐ｄ汉鐨勪换鍔°€?                    or not can_start(task.id)):  # 鍚屾椂瑕佹眰鍓嶇疆渚濊禆鍏ㄩ儴瀹屾垚銆?                continue  # 涓嶇鍚堟潯浠舵椂妫€鏌ヤ笅涓€涓换鍔°€?            _, error = task_worktree_cwd(task)  # 楠岃瘉浠诲姟缁戝畾鐨勫伐浣滅洰褰曘€?            if not error:  # 宸ヤ綔鐩綍鏃犻敊璇椂銆?                ready.append(task)  # 鍔犲叆鍙鍙栧垪琛ㄣ€?        return ready  # 杩斿洖灏辩华浠诲姟銆?

def claim_next_task(name: str) -> Task | None:  # 涓洪槦鍙嬭棰嗕笅涓€涓彲鎵ц浠诲姟锛涙渶鏃╋細13.1136 鈭?    """Claim the first still-available task, never a second assignment.锝滀腑鏂囷細璁ら绗竴涓粛鍙敤鐨勪换鍔★紝涓斾笉閲嶅鍒嗛厤绗簩涓换鍔°€?""
    with task_lock:  # 鎸侀攣妫€鏌ラ槦鍙嬪綋鍓嶅垎閰嶃€?        if teammate_assignments.get(name) or _owner_in_progress(name):  # 宸叉湁鐩綍鍒嗛厤鎴栬繘琛屼腑浠诲姟鏃朵笉鍐嶉鍙栥€?            return None  # 杩斿洖鏃犲彲棰嗗彇浠诲姟銆?    for task in scan_unclaimed_tasks():  # 閬嶅巻褰撳墠鍙鍙栦换鍔°€?        result = claim_task(task.id, owner=name)  # 灏濊瘯浠ヨ闃熷弸韬唤棰嗗彇銆?        if result.startswith("Claimed "):  # 棰嗗彇鎴愬姛鏃躲€?            return load_task(task.id)  # 閲嶆柊璇诲彇骞惰繑鍥炲凡棰嗗彇浠诲姟銆?    return None  # 娌℃湁鎴愬姛棰嗗彇鏃惰繑鍥?None銆?

def _last_assistant_text(content) -> str:  # 鎻愬彇闃熷弸鍝嶅簲涓涓€娈垫ā鍨嬫枃鏈紱鏈€鏃╋細13.992 鈭?    for block in content:  # 鎸夊唴瀹瑰潡椤哄簭鏌ユ壘鏂囨湰銆?        if getattr(block, "type", None) == "text":  # 璇嗗埆 SDK 鏂囨湰鍧楀璞°€?            return block.text.strip()  # 杩斿洖璇ユ枃鏈潡骞跺幓闄や袱绔┖鐧姐€?        if isinstance(block, dict) and block.get("type") == "text":  # 鍏煎瀛楀吀褰㈠紡鐨勬枃鏈潡銆?            return str(block.get("text", "")).strip()  # 杩斿洖瀛楀吀涓殑鏂囨湰銆?    return ""  # 娌℃湁鏂囨湰鏃惰繑鍥炵┖瀛楃涓层€?

def current_work_identity(owner: str) -> tuple[int, str | None]:  # 璇诲彇璐熻矗浜哄綋鍓嶅垎閰嶇増鏈拰浠诲姟鍙凤紱鏈€鏃╋細13.1001 鈭?    with task_lock:  # 鎸侀攣璇诲彇浠诲姟韬唤銆?        assignment = teammate_assignments.get(owner)  # 鏌ユ壘璐熻矗浜虹殑鍒嗛厤蹇収銆?        task_id = str(assignment["task_id"]) if assignment else None  # 鎻愬彇浠诲姟 ID锛屾棤鍒嗛厤鏃朵负 None銆?        return assignment_versions.get(owner, 0), task_id  # 杩斿洖鍒嗛厤鐗堟湰鍜屼换鍔?ID銆?

def _run_teammate_tool(name: str, block, handlers: dict) -> str:  # 鍦ㄩ槦鍙嬫潈闄愬拰浠诲姟鐩綍涓嬫墽琛屽伐鍏凤紱鏈€鏃╋細13.1035 鈭?    gate = plan_gates.get(name, "not_required")  # 璇诲彇闃熷弸璁″垝闂ㄦ帶锛岄粯璁や笉瑕佹眰璁″垝銆?    if (block.name in {"bash", "write_file", "edit_file"}  # 瀵?Shell 鍜屽啓鍏ョ被宸ュ叿妫€鏌ヨ鍒掗棬鎺с€?            and gate not in {"not_required", "approved"}):  # 鍙湪涓嶈姹傝鍒掓垨宸叉壒鍑嗘椂鏀捐銆?        return f"Blocked: plan status is {gate}."  # 杩斿洖闂ㄦ帶闃绘鍘熷洜銆?    blocked = trigger_hooks("PreToolUse", block)  # 宸ュ叿鎵ц鍓嶈繍琛屾潈闄愮瓑閽╁瓙銆?    if blocked is not None:  # 閽╁瓙杩斿洖鎷︽埅缁撴灉鏃躲€?        return str(blocked)  # 灏嗘嫤鎴師鍥犺繑鍥炵粰妯″瀷銆?    handler = handlers.get(block.name)  # 鎸夊伐鍏峰悕鏌ユ壘澶勭悊鍣ㄣ€?    output = call_tool_handler(handler, block.input, block.name)  # 璋冪敤宸ュ叿骞剁粺涓€澶勭悊寮傚父銆?    trigger_hooks("PostToolUse", block, output)  # 鎵ц宸ュ叿鍚庣殑鍏叡閽╁瓙銆?    return str(output)  # 灏嗙粨鏋滆浆鎴愭枃鏈繑鍥炪€?

def apply_plan_response(name: str, msg: dict) -> tuple[bool, str]:  # 澶勭悊 Lead 瀵归槦鍙嬭鍒掔殑瀹℃壒缁撴灉锛涙渶鏃╋細13.1057 鈭?    """Apply only the Lead response for this teammate's current plan.锝滀腑鏂囷細浠呭簲鐢?Lead 閽堝璇ラ槦鍙嬪綋鍓嶈鍒掍綔鍑虹殑鍝嶅簲銆?""
    metadata = msg.get("metadata", {})  # 璇诲彇鍝嶅簲鍏冩暟鎹€?    request_id = metadata.get("request_id", "")  # 鎻愬彇鍏宠仈鐨勫鎵硅姹?ID銆?    work_version, task_id = current_work_identity(name)  # 鑾峰彇闃熷弸褰撳墠浠诲姟鍜屽垎閰嶇増鏈€?    with team_lock:  # 鎸侀攣鏍搁獙骞舵洿鏂板洟闃熺姸鎬併€?        state = pending_requests.get(request_id)  # 鎸夎姹?ID 鏌ユ壘鍗忚璁板綍銆?        expected_id = plan_request_ids.get(name)  # 璇诲彇闃熷弸褰撳墠绛夊緟鐨勮鍒掕姹?ID銆?        valid = (  # 閫愰」鏍稿娑堟伅鍜岃姹傜姸鎬併€?            msg.get("from") == "lead"  # 鍝嶅簲蹇呴』鏉ヨ嚜 Lead銆?            and msg.get("to") == name  # 鍝嶅簲蹇呴』鍙戦€佺粰褰撳墠闃熷弸銆?            and request_id == expected_id  # 璇锋眰 ID 蹇呴』鏄綋鍓嶈鍒掔殑 ID銆?            and state is not None  # 鍗忚璁板綍蹇呴』瀛樺湪銆?            and state.type == "plan_approval"  # 璇锋眰绫诲瀷蹇呴』鏄鍒掑鎵广€?            and state.sender == name  # 鍘熻鍒掓彁浜ゆ柟蹇呴』鏄綋鍓嶉槦鍙嬨€?            and state.target == "lead"  # 鍘熻鍒掓帴鏀舵柟蹇呴』鏄?Lead銆?            and state.work_version == work_version  # 鍒嗛厤鐗堟湰蹇呴』涓庡綋鍓嶅伐浣滀竴鑷淬€?            and state.task_id == task_id  # 浠诲姟 ID 蹇呴』涓庡綋鍓嶅伐浣滀竴鑷淬€?            and state.status in {"approved", "rejected"}  # 鍗忚璁板綍蹇呴』宸茬粡鎵瑰噯鎴栨嫆缁濄€?            and metadata.get("approve", False)  # 璇诲彇鍝嶅簲涓殑鎵瑰噯鏍囪銆?            == (state.status == "approved")  # 鎵瑰噯鏍囪椤讳笌鍗忚鐘舵€佷竴鑷淬€?        )  # 瀹屾垚鍝嶅簲鏍￠獙銆?        if not valid:  # 浠讳竴鏉′欢涓嶇鏃跺拷鐣ュ搷搴斻€?            return False, "[Ignored plan response: request mismatch]"  # 杩斿洖涓嶅尮閰嶆彁绀恒€?        plan_gates[name] = state.status  # 灏嗗鎵圭粨鏋滃簲鐢ㄥ埌璁″垝闂ㄦ帶銆?        active_teammates[name] = "working"  # 灏嗛槦鍙嬬姸鎬佽涓哄伐浣滀腑銆?        plan_request_ids.pop(name, None)  # 绉婚櫎宸插鐞嗙殑褰撳墠璇锋眰 ID銆?        outcome = state.status  # 璁板綍缁撴灉渚涢攣澶栬繑鍥炪€?    return True, f"[Plan {outcome}] {msg['content']}"  # 杩斿洖澶勭悊鎴愬姛鍜屽鎵硅鏄庛€?

def apply_shutdown_request(name: str, msg: dict) -> tuple[bool, str]:  # 澶勭悊 Lead 鍙戠粰闃熷弸鐨勫叧闂姹傦紱鏈€鏃╋細13.1088  鈭?    """Accept only a pending shutdown request sent by Lead to this teammate.锝滀腑鏂囷細浠呮帴鍙?Lead 鍙戠粰璇ラ槦鍙嬩笖浠嶅緟澶勭悊鐨勫叧闂姹傘€?""
    request_id = msg.get("metadata", {}).get("request_id", "")  # 浠庢秷鎭厓鏁版嵁璇诲彇璇锋眰 ID銆?    with team_lock:  # 鎸侀攣鏍搁獙鍏抽棴璇锋眰銆?        state = pending_requests.get(request_id)  # 鏌ユ壘瀵瑰簲鍗忚璁板綍銆?        valid = (  # 閫愰」妫€鏌ヨ姹傛槸鍚﹀悎娉曘€?            msg.get("from") == "lead"  # 娑堟伅蹇呴』鏉ヨ嚜 Lead銆?            and msg.get("to") == name  # 娑堟伅蹇呴』鍙戠粰褰撳墠闃熷弸銆?            and state is not None  # 鍗忚璁板綍蹇呴』瀛樺湪銆?            and state.type == "shutdown"  # 璇锋眰绫诲瀷蹇呴』鏄叧闂€?            and state.sender == "lead"  # 鍘熻姹傚彂閫佹柟蹇呴』鏄?Lead銆?            and state.target == name  # 鍘熻姹傜洰鏍囧繀椤绘槸褰撳墠闃熷弸銆?            and state.status == "pending"  # 璇锋眰蹇呴』浠嶅緟澶勭悊銆?            and active_teammates.get(name) != "stopping"  # 闃熷弸涓嶈兘宸茬粡杩涘叆鍏抽棴鐘舵€併€?        )  # 瀹屾垚鍏抽棴璇锋眰鏍￠獙銆?        if not valid:  # 鏍￠獙澶辫触鏃跺拷鐣ヨ姹傘€?            return False, "[Ignored shutdown request: request mismatch]"  # 杩斿洖涓嶅尮閰嶆彁绀恒€?        active_teammates[name] = "stopping"  # 灏嗛槦鍙嬫爣璁颁负姝ｅ湪鍏抽棴銆?    return True, request_id  # 杩斿洖鎺ュ彈缁撴灉鍙婅姹?ID銆?

def _teammate_send_message(from_name: str, to: str, content: str) -> str:  # 鎸夊洟闃熷崗璁彂閫侀槦鍙嬫秷鎭紱鏈€鏃╋細13.1109 鈭?    with team_lock:  # 鎸侀攣妫€鏌ユ帴鏀舵柟鐘舵€併€?        if to != "lead" and to not in active_teammates:  # 鎺ユ敹鏂归』涓?Lead 鎴栨椿璺冮槦鍙嬨€?            return f"Agent '{to}' is not active"  # 鎺ユ敹鏂逛笉娲昏穬鏃舵嫆缁濆彂閫併€?    BUS.send(from_name, to, content)  # 閫氳繃娑堟伅鎬荤嚎鍐欏叆鎺ユ敹鏂归偖绠便€?    return f"Sent to {to}"  # 杩斿洖鍙戦€佺粨鏋溿€?

# -- Teammate Thread --锝滈槦鍙嬬嚎绋嬶細缁ф壙绗?13 绔狅紝涓烘瘡鍚嶉槦鍙嬭繍琛岀嫭绔?Agent 寰幆涓庡伐鍏蜂笂涓嬫枃銆?
def spawn_teammate_thread(name: str, role: str, prompt: str,  # 鍚姩鍏锋湁鐙珛涓婁笅鏂囩殑闃熷弸绾跨▼锛涙渶鏃╋細13.1381 鈭?                          task_id: str | None = None,  # 鍙€夊湴棰勫垎閰嶄换鍔°€?                          require_plan: bool = False) -> str:  # 鍙€夊湴瑕佹眰鍏堟彁浜よ鍒掋€?    if not is_valid_agent_name(name):  # 楠岃瘉闃熷弸鍚嶇О鏍煎紡銆?        return ("Invalid teammate name: use 1-64 letters, digits, "  # 杩斿洖鍚嶇О鏍煎紡瑕佹眰銆?                "underscores, or dashes")  # 璇存槑鍏佽浣跨敤鐨勫瓧绗︺€?    if name.lower() in RESERVED_TEAMMATE_NAMES:  # 淇濈暀鍚嶇О涓嶅彲鐢ㄤ簬闃熷弸銆?        return f"Invalid teammate name: '{name}' is reserved by the runtime"  # 杩斿洖鍚嶇О淇濈暀鎻愮ず銆?    with team_lock:  # 鎸侀攣妫€鏌ュ苟鐧昏闃熷弸銆?        if any(existing.casefold() == name.casefold()  # 蹇界暐澶у皬鍐欐鏌ュ凡鏈夊悕绉般€?               for existing in active_teammates):  # 閬嶅巻娲昏穬闃熷弸銆?            return f"Teammate '{name}' already exists"  # 鍚嶇О鍐茬獊鏃舵嫆缁濆惎鍔ㄣ€?        active_teammates[name] = "working"  # 鐧昏鍒濆宸ヤ綔鐘舵€併€?        plan_gates[name] = "required" if require_plan else "not_required"  # 鏍规嵁鍙傛暟鍒濆鍖栬鍒掗棬鎺с€?        assignment_versions[name] = 0  # 鍒濆鍖栦换鍔″垎閰嶇増鏈€?
    if task_id:  # 鎸囧畾鍒濆浠诲姟鏃跺厛璁ら銆?        try:  # 澶勭悊浠诲姟璇诲彇鍙婃牎楠岄敊璇€?            claimed = claim_task(task_id, owner=name)  # 浠ラ槦鍙嬭韩浠借棰嗕换鍔°€?        except (FileNotFoundError, ValueError) as exc:  # 浠诲姟涓嶅瓨鍦ㄦ垨鏃犳晥鏃躲€?            claimed = f"Error: {exc}"  # 灏嗗紓甯告暣鐞嗕负閿欒鏂囨湰銆?        if not claimed.startswith("Claimed "):  # 棰嗗彇鏈垚鍔熸椂鎾ら攢娉ㄥ唽銆?            with team_lock:  # 鎸侀攣娓呯悊闃熷弸鐘舵€併€?                active_teammates.pop(name, None)  # 绉婚櫎娲昏穬闃熷弸璁板綍銆?                plan_gates.pop(name, None)  # 绉婚櫎璁″垝闂ㄦ帶銆?                assignment_versions.pop(name, None)  # 绉婚櫎鍒嗛厤鐗堟湰銆?            return f"Cannot spawn teammate '{name}': {claimed}"  # 杩斿洖鍚姩澶辫触鍘熷洜銆?
    system = (f"浣犳槸鍚嶄负鈥渰name}鈥濈殑闃熷弸锛岃鑹叉槸鈥渰role}鈥濄€?  # 鏋勯€犻槦鍙嬩笓鐢ㄧ郴缁熸彁绀鸿瘝銆?              "璇蜂娇鐢ㄥ伐鍏峰畬鎴愪换鍔°€備綘鍙互鏌ョ湅浠诲姟鏉垮苟璁ら浠诲姟銆?  # 璇存槑鎵ц浠诲姟鍜屼娇鐢ㄤ换鍔℃澘銆?              "濡傛灉鍒濆娑堟伅鍖呭惈銆愬凡鍒嗛厤浠诲姟銆戯紝璇存槑璇ヤ换鍔″凡缁忚璁ら锛屼笉瑕佸啀娆¤皟鐢?claim_task銆?  # 鎻愰啋宸插垎閰嶄换鍔℃棤闇€閲嶅璁ら銆?              "杩愯鏃朵細璁╂墍鏈夋枃浠剁郴缁熷伐鍏峰湪宸茶棰嗕换鍔＄殑宸ヤ綔鐩綍涓墽琛屻€?  # 璇存槑宸ュ叿浣跨敤浠诲姟宸ヤ綔鐩綍銆?              "濡傛灉琚姹傚厛鎻愪氦璁″垝锛屽繀椤诲湪璋冪敤 bash銆亀rite_file 鎴?edit_file 鍓嶆彁浜よ鍒掑苟绛夊緟鎵瑰噯銆?  # 璇存槑璁″垝瀹℃壒鍓嶇殑宸ュ叿闄愬埗銆?              "杩愯鏃朵細鎶婁綘鐨勬渶缁堟枃鏈氦缁?Lead銆俿end_message 鍙敤浜庤繃绋嬩腑鐨勫崗璋冩秷鎭紝"  # 璇存槑鏈€缁堢粨鏋滀笌鍗忚皟娑堟伅鐨勭敤閫斻€?              "骞跺缁堜娇鐢ㄢ€渓ead鈥濈О鍛煎崗璋冭€呫€?)  # 绾﹀畾鍗忚皟鑰呭悕绉般€?
    def handle_inbox_message(name: str, msg: dict, messages: list):  # 澶勭悊闃熷弸鏈疆鏀跺埌鐨勫崗璁秷鎭紱鏈€鏃╋細15.1383 鈭?        msg_type = msg.get("type", "message")  # 鏈０鏄庣被鍨嬫椂鎸夋櫘閫氭秷鎭鐞嗭紝鍏煎绗?13 绔犳棭鏈熼偖绠辫褰曘€?        meta = msg.get("metadata", {})  # 瀹℃壒绫诲崗璁妸鍏宠仈淇℃伅鏀惧湪 metadata锛屾鏂囧彧淇濈暀缁欐ā鍨嬮槄璇荤殑鍐呭銆?        req_id = meta.get("request_id", "")  # 璇锋眰 ID 灏嗗紓姝ュ搷搴旂粦瀹氬埌鍘熻姹傦紝閬垮厤鏃у鎵硅浣滅敤浜庢柊璁″垝銆?
        if msg_type == "shutdown_request":  # 鍏抽棴璇锋眰鏄帶鍒跺崗璁紝涓嶈兘鍍忔櫘閫氭枃鏈竴鏍蜂氦缁欐ā鍨嬭嚜鐢辫В閲娿€?            accepted, notice = apply_shutdown_request(name, msg)  # 鏍￠獙鍙戦€佽€呫€佹帴鏀惰€呭拰寰呭鐞嗚姹傛槸鍚﹀尮閰嶃€?            if not accepted:  # 杩囨湡銆佷吉閫犳垨鍙戦敊瀵硅薄鐨勮姹備笉浼氱粓姝㈢嚎绋嬨€?                messages.append({"role": "user", "content": notice})  # 鎶婃嫆缁濆師鍥犲弽棣堢粰闃熷弸妯″瀷锛屼繚鐣欏崗璁彲瑙佹€с€?                return False  # 杩斿洖 False 琛ㄧず鏈疆缁х画杩愯銆?            req_id = notice  # 鏍￠獙鎴愬姛鏃?notice 鏄鑼冨寲璇锋眰 ID锛岀敤瀹冩瀯閫犲搴斿搷搴斻€?            BUS.send(name, "lead", "Shutting down gracefully.",  # 鍚?Lead 鍙戦€佸叧闂‘璁ゃ€?                     "shutdown_response",  # 璁剧疆鍏抽棴鍝嶅簲绫诲瀷銆?                     {"request_id": req_id, "approve": True})  # 鍏堢‘璁ゅ叧闂紝Lead 鎵嶈兘鍖哄垎姝ｅ父閫€鍑轰笌绾跨▼鏁呴殰銆?            print(f"  \033[35m[protocol] {name} approved shutdown "  # 杈撳嚭鍏抽棴纭鏃ュ織銆?                  f"({req_id})\033[0m")  # 闄勪笂鍏宠仈璇锋眰缂栧彿銆?            return True  # True 鍙〃杈锯€滃簲閫€鍑哄惊鐜€濓紝鐪熸鐨勮祫婧愬洖鏀剁粺涓€浜ょ粰 run() 鐨?finally銆?
        if msg_type == "plan_approval_response":  # 璁″垝瀹℃壒浼氭敼鍙樺啓宸ュ叿鐨勯棬绂佺姸鎬侊紝蹇呴』璧板崗璁姸鎬佹満銆?            _, notice = apply_plan_response(name, msg)  # 鍙帴鍙楀綋鍓嶄换鍔＄増鏈搴旂殑 Lead 鍝嶅簲銆?            messages.append({"role": "user",  # 灏嗗崗璁鐞嗙粨鏋滃姞鍏ラ槦鍙嬪巻鍙层€?                "content": notice})  # 灏嗘壒鍑嗘垨鎷掔粷鍘熷洜浣滀负鏂扮敤鎴锋秷鎭氦缁欓槦鍙嬬户缁喅绛栥€?        elif msg_type == "plan_request":  # Lead 鍙湪闃熷弸杩愯涓复鏃惰姹傚厛瑙勫垝鍐嶆墽琛屻€?            messages.append({"role": "user",  # 灏嗚鍒掕姹傚姞鍏ラ槦鍙嬪巻鍙层€?                "content": f"[闇€瑕佽鍒抅 {msg['content']}"})  # 鏄庣‘鏍囪涓烘帶鍒惰姹傦紝閬垮厤涓庢櫘閫氬崗浣滄枃鏈贩娣嗐€?        elif msg_type == "message":  # 鏅€氭秷鎭笉鏀瑰彉鍗忚鐘舵€侊紝鍙ˉ鍏呴槦鍙嬩笂涓嬫枃銆?            messages.append({"role": "user",  # 灏嗗崗璋冩秷鎭姞鍏ラ槦鍙嬪巻鍙层€?                "content": f"[Message from {msg['from']}] {msg['content']}"})  # 淇濈暀鏉ユ簮锛屼究浜庢ā鍨嬪垽鏂崗璋冨璞°€?        return False  # 闄ゅ凡纭鍏抽棴澶栵紝鍏朵綑娑堟伅閮借闃熷弸缁х画涓嬩竴杞€?
    def run_loop():  # 杩愯闃熷弸鐨勬ā鍨嬩笌宸ュ叿寰幆锛涙渶鏃╋細15.1413 鈭?        def current_cwd() -> tuple[Path | None, str | None]:  # 鍙栧緱闃熷弸褰撳墠浠诲姟鐩綍锛涙渶鏃╋細15.1414 鈭?            if name not in teammate_assignments:  # 闃熷弸蹇呴』鍏堟嫢鏈変换鍔★紝鏂囦欢鎿嶄綔鎵嶆湁鏄庣‘璐ｄ换杈圭晫鍜岀洰褰曞熀鍑嗐€?                return None, "Error: Claim a Task before using workspace tools."  # 浠ュ伐鍏风粨鏋滄嫆缁濓紝鑰屼笉鏄粯璁ら€€鍥炰富宸ヤ綔鍖恒€?            try:  # 姣忔璋冪敤閮介噸鏂拌В鏋愶紝鍙婃椂鍙戠幇宸ヤ綔鏍戣澶栭儴鍒犻櫎鎴栫粦瀹氭崯鍧忋€?                return assignment_cwd(name), None  # 姝ｅ父璺緞鍚屾椂杩斿洖鐩綍鍜岀┖閿欒锛屾柟渚垮寘瑁呭櫒缁熶竴鐭矾銆?            except (FileNotFoundError, ValueError) as exc:  # 灏嗕换鍔℃垨宸ヤ綔鏍戠姸鎬侀敊璇浆鎹负妯″瀷鍙鐞嗙殑鏂囨湰銆?                return None, f"Error: Invalid task assignment: {exc}"  # 澶辫触鏃剁粷涓嶆彁渚涘洖閫€鐩綍锛岄噰鐢?fail-closed 绛栫暐銆?
        def _run_bash(command: str) -> str:  # 鍦ㄩ槦鍙嬪綋鍓嶄换鍔＄洰褰曟墽琛?Shell锛涙渶鏃╋細15.1422 鈭?            cwd, error = current_cwd()  # Shell 涓庢枃浠跺伐鍏峰叡浜浉鍚岀殑浠诲姟鐩綍瑙ｆ瀽瑙勫垯銆?            return error or run_bash(command, cwd=cwd)  # 鏈夐敊璇氨鐩存帴鍙嶉锛涘惁鍒欐樉寮忎紶鍏ヤ换鍔?cwd锛岄伩鍏嶈繘绋嬬骇 chdir 绔炴€併€?
        def _run_read(path: str, limit: int | None = None,  # 璇诲彇闃熷弸褰撳墠浠诲姟鐩綍涓殑鏂囦欢锛涙渶鏃╋細15.1426 鈭?                      offset: int = 0) -> str:  # 鏀寔鎸夊亸绉诲拰琛屾暟璇诲彇銆?            cwd, error = current_cwd()  # 璇诲彇涔熷彈浠诲姟鐩綍绾︽潫锛岄槻姝㈤槦鍙嬫棤浠诲姟鏃舵祻瑙堜富宸ヤ綔鍖恒€?            return error or run_read(path, limit=limit, offset=offset, cwd=cwd)  # 淇濈暀鍒嗛〉鍙傛暟锛屽悓鏃舵妸鐩稿璺緞閿氬畾鍒颁换鍔?cwd銆?
        def _run_write(path: str, content: str) -> str:  # 鍐欏叆闃熷弸褰撳墠浠诲姟鐩綍涓殑鏂囦欢锛涙渶鏃╋細15.1431 鈭?            cwd, error = current_cwd()  # 鍐欏叆鍓嶅啀娆＄‘璁ゅ綋鍓嶅垎閰嶏紝閬垮厤瀹屾垚浠诲姟鍚庣户缁娇鐢ㄦ棫鐩綍銆?            return error or run_write(path, content, cwd=cwd)  # 瀹為檯璺緞瀹夊叏浠嶇敱鍩虹宸ュ叿鐨?safe_path 缁熶竴妫€鏌ャ€?
        def _run_edit(path: str, old_text: str, new_text: str) -> str:  # 缂栬緫闃熷弸褰撳墠浠诲姟鐩綍涓殑鏂囦欢锛涙渶鏃╋細15.1435 鈭?            cwd, error = current_cwd()  # 缂栬緫鎿嶄綔涓庡啓鍏ヤ娇鐢ㄥ悓涓€绉熺害锛屼笉鍗曠嫭缂撳瓨宸ヤ綔鏍戣矾寰勩€?            return error or run_edit(path, old_text, new_text, cwd=cwd)  # 绮剧‘鏇挎崲閫昏緫澶嶇敤鍩虹宸ュ叿锛屼粎娉ㄥ叆闃熷弸浣滅敤鍩熴€?
        def _run_glob(pattern: str) -> str:  # 鎼滅储闃熷弸褰撳墠浠诲姟鐩綍涓殑鏂囦欢锛涙渶鏃╋細15.143 9 鈭?            cwd, error = current_cwd()  # 鎼滅储缁撴灉涔熷繀椤诲眬闄愪簬闃熷弸璐熻矗鐨勪换鍔＄洰褰曘€?            return error or run_glob(pattern, cwd=cwd)  # 鎶婇殧绂荤瓥鐣ユ斁鍦ㄥ寘瑁呭眰锛岄伩鍏嶅鍒?glob 瀹炵幇銆?
        def _run_list_tasks():  # 鍚戦槦鍙嬪垪鍑哄彲瑙佷换鍔★紱鏈€鏃╋細15.1443 鈭?            tasks = list_tasks()  # 浠庡叡浜寔涔呬换鍔℃澘璇诲彇锛屽洜姝ら槦鍙嬭兘鐪嬪埌鍏朵粬绾跨▼鍒氬畬鎴愭垨閲婃斁鐨勪换鍔°€?            if not tasks:  # 鏄惧紡鍖哄垎绌轰换鍔℃澘涓庡伐鍏峰紓甯搞€?                return "No tasks."  # 杩斿洖鐭枃鏈紝渚夸簬妯″瀷鍐冲畾绛夊緟鎴栭€氱煡 Lead銆?            return "\n".join(  # 灏嗕换鍔′俊鎭嫾鎴愬琛屻€?                f"  {t.id}: {t.subject} [{t.status}]"  # 灞曠ず浠诲姟缂栧彿銆佷富棰樺拰鐘舵€併€?                + (f" (wt:{t.worktree})" if t.worktree else "")  # 鏈夌粦瀹氬伐浣滄爲鏃堕檮涓婂悕绉般€?                for t in tasks)  # 閬嶅巻褰撳墠浠诲姟蹇収銆?
        def _run_claim_task(task_id: str):  # 璁╅槦鍙嬭棰嗘寚瀹氫换鍔★紱鏈€鏃╋細15.1452 鈭?            try:  # 璁ら鍐呴儴宸叉寔閿佸苟鏍￠獙渚濊禆锛岃繖閲屽彧鎶婂紓甯搁€傞厤鎴愬伐鍏风粨鏋溿€?                return claim_task(task_id, owner=name)  # owner 浣跨敤绾跨▼瀵瑰簲鍚嶇О锛屽缓绔嬩换鍔°€侀槦鍙嬪拰 cwd 鐨勭粦瀹氥€?            except ValueError as exc:  # 鎹曡幏渚濊禆鏈畬鎴愩€佸凡鏈変换鍔＄瓑鍙慨姝ｇ殑涓氬姟閿欒銆?                return f"Error: {exc}"  # 璁╂ā鍨嬬湅鍒板師鍥犲悗閲嶆柊閫夋嫨浠诲姟銆?            except FileNotFoundError:  # 浠诲姟鍙兘鍒氳鍏朵粬鍙備笌鑰呭垹闄ゆ垨杈撳叆 ID 鏈夎銆?                return f"Error: Task {task_id} not found"  # 涓嶈鏂囦欢寮傚父閫冮€稿苟鏉€姝婚槦鍙嬬嚎绋嬨€?
        def _run_complete_task(task_id: str):  # 璁╅槦鍙嬪畬鎴愬苟閲婃斁褰撳墠浠诲姟锛涙渶鏃╋細15.1460 鈭?            try:  # 瀹屾垚鎿嶄綔浼氶獙璇?owner锛屼笉鑳界敱闃熷弸鏇垮叾浠栫嚎绋嬪叧闂换鍔°€?                return complete_task(task_id, owner=name)  # 鎸佷箙鍖栧畬鎴愮姸鎬侊紝闅忓悗绌洪棽寰幆鎵嶅彲璁ら鏂颁换鍔°€?            except ValueError as exc:  # 鎵€鏈夋潈鎴栫姸鎬佷笉鍚堟硶鏃朵繚鐣欏綋鍓嶅垎閰嶏紝绛夊緟妯″瀷绾犳銆?                return f"Error: {exc}"  # 灏嗛鍩熼敊璇€佸洖宸ュ叿鍙嶉寰幆銆?            except FileNotFoundError:  # 澶勭悊浠诲姟璁板綍鎰忓娑堝け鐨勭珵浜夋儏鍐点€?                return f"Error: Task {task_id} not found"  # 淇濇寔绾跨▼瀛樻椿锛屾渶缁堟竻鐞嗙敱澶栧眰 run 璐熻矗銆?
        initial_prompt = prompt  # 浠?Lead 鐨勫娲捐鏄庡紑濮嬫瀯閫犻槦鍙嬬嫭绔嬩笂涓嬫枃锛屼笉缁ф壙涓?Agent 鐨勫畬鏁村巻鍙层€?        if task_id:  # 鏄惧紡鍒嗛厤浠诲姟鏃讹紝灏嗘寔涔呬换鍔¤褰曡浆鎴愰槦鍙嬬殑鏉冨▉宸ヤ綔璇存槑銆?            task = load_task(task_id)  # 閲嶆柊浠庝换鍔″瓨鍌ㄨ鍙栵紝閬垮厤浣跨敤璁ら鍓嶅彲鑳藉凡杩囨湡鐨勮皟鐢ㄥ弬鏁般€?            initial_prompt += (  # 娉ㄥ叆浠诲姟 ID銆佺洰鏍囥€佹弿杩板拰瑙ｆ瀽鍚庣殑瀹為檯鐩綍锛岃妯″瀷鐭ラ亾鎵ц杈圭晫銆?                f"\n\n[宸插垎閰嶄换鍔?{task.id}] {task.subject}\n"  # 鍐欏叆鍒嗛厤浠诲姟鐨勭紪鍙峰拰涓婚銆?                f"{task.description}\n宸ヤ綔鐩綍锛歿assignment_cwd(name)}"  # 鍐欏叆浠诲姟鎻忚堪鍜屽伐浣滅洰褰曘€?            )  # 缁撴潫鍒濆浠诲姟璇存槑銆?        if require_plan:  # 璁″垝闂ㄧ涓嶄粎瀛樺湪浜庣郴缁熸彁绀鸿瘝锛屼篃浣滀负褰撳墠璇锋眰涓殑鏄惧紡瑕佹眰鍐嶆鍛堢幇銆?            initial_prompt += ("\n\n[闇€瑕佽鍒抅 璇峰厛鎻愪氦璁″垝骞剁瓑寰?Lead 鎵瑰噯锛?  # 鍚戦槦鍙嬫槑纭渶瑕佸厛鎻愪氦璁″垝銆?                               "鑾锋壒鍓嶄笉寰楄皟鐢?bash銆亀rite_file 鎴?edit_file銆?)  # 鍒楀嚭瀹℃壒鍓嶅彈闄愮殑宸ュ叿銆?        messages = [{"role": "user", "content": initial_prompt}]  # 姣忓悕闃熷弸鎷ユ湁鐙珛娑堟伅鍘嗗彶锛岄伩鍏嶅苟琛岀嚎绋嬩簰鐩告薄鏌撲笂涓嬫枃銆?        sub_tools = [  # 闃熷弸鍙幏寰楀畬鎴愪换鍔″拰鍗忚皟鎵€闇€鐨勬渶灏忓伐鍏烽泦锛屼笉缁ф壙 Lead 鐨勫洟闃熺鐞嗘潈闄愩€?            {"name": "bash", "description": "杩愯涓€鏉?Shell 鍛戒护銆?,  # 瀹氫箟 Shell 宸ュ叿銆?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {"command": {"type": "string"}},  # 瀹氫箟鍛戒护瀛楃涓插弬鏁般€?                              "required": ["command"]}},  # 鍛戒护鍙傛暟蹇呭～銆?            {"name": "read_file", "description": "璇诲彇鏂囦欢銆?,  # 瀹氫箟鏂囦欢璇诲彇宸ュ叿銆?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {  # 寮€濮嬪畾涔夎鍙栧弬鏁般€?                                  "path": {"type": "string"},  # 鏂囦欢璺緞鍙傛暟銆?                                  "limit": {"type": "integer"},  # 鍙€夎鍙栬鏁般€?                                  "offset": {"type": "integer"}},  # 鍙€夎捣濮嬭鍋忕Щ銆?                              "required": ["path"]}},  # 鏂囦欢璺緞蹇呭～銆?            {"name": "write_file", "description": "鍐欏叆鏂囦欢銆?,  # 瀹氫箟鏂囦欢鍐欏叆宸ュ叿銆?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {"path": {"type": "string"},  # 瀹氫箟鏂囦欢璺緞鍙傛暟銆?                                             "content": {"type": "string"}},  # 瀹氫箟鍐欏叆鍐呭鍙傛暟銆?                              "required": ["path", "content"]}},  # 璺緞鍜屽唴瀹瑰繀濉€?            {"name": "edit_file", "description": "鏇挎崲鏂囦欢涓殑鎸囧畾鏂囨湰銆?,  # 瀹氫箟鏂囦欢缂栬緫宸ュ叿銆?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {  # 寮€濮嬪畾涔夌紪杈戝弬鏁般€?                                  "path": {"type": "string"},  # 鏂囦欢璺緞鍙傛暟銆?                                  "old_text": {"type": "string"},  # 寰呮浛鎹㈡枃鏈弬鏁般€?                                  "new_text": {"type": "string"}},  # 鏇挎崲鍚庣殑鏂囨湰鍙傛暟銆?                              "required": ["path", "old_text", "new_text"]}},  # 涓変釜缂栬緫鍙傛暟鍧囧繀濉€?            {"name": "glob", "description": "鎸?glob 妯″紡鏌ユ壘鏂囦欢锛?* 琛ㄧず閫掑綊鍖归厤銆?,  # 瀹氫箟鏂囦欢鎼滅储宸ュ叿銆?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {  # 寮€濮嬪畾涔夋悳绱㈠弬鏁般€?                                  "pattern": {"type": "string"}},  # 鎸囧畾鍖归厤妯″紡銆?                              "required": ["pattern"]}},  # 鍖归厤妯″紡蹇呭～銆?            {"name": "send_message",  # 瀹氫箟鍥㈤槦娑堟伅宸ュ叿銆?             "description": "鍚?lead 鎴栧綋鍓嶆椿璺冪殑闃熷弸鍙戦€佽繃绋嬪崗璋冩秷鎭€?,  # 璇存槑娑堟伅鐢ㄤ簬杩囩▼鍗忚皟銆?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {"to": {"type": "string"},  # 瀹氫箟鎺ユ敹鏂瑰弬鏁般€?                                             "content": {"type": "string"}},  # 瀹氫箟娑堟伅鍐呭鍙傛暟銆?                              "required": ["to", "content"]}},  # 鎺ユ敹鏂瑰拰鍐呭蹇呭～銆?            {"name": "submit_plan",  # 瀹氫箟璁″垝鎻愪氦宸ュ叿銆?             "description": "鎻愪氦璁″垝骞剁瓑寰?Lead 瀹℃壒銆?,  # 璇存槑鎻愪氦鍚庣瓑寰?Lead 瀹℃壒銆?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {"plan": {"type": "string"}},  # 瀹氫箟璁″垝鏂囨湰鍙傛暟銆?                              "required": ["plan"]}},  # 璁″垝鏂囨湰蹇呭～銆?            {"name": "list_tasks",  # 瀹氫箟浠诲姟鍒楄〃宸ュ叿銆?             "description": "鍒楀嚭浠诲姟鏉夸笂鐨勫叏閮ㄤ换鍔°€?,  # 璇存槑鍏惰繑鍥炰换鍔℃澘鍐呭銆?             "input_schema": {"type": "object", "properties": {},  # 澹版槑鏃犲睘鎬х殑瀵硅薄杈撳叆銆?                              "required": []}},  # 涓嶈姹傝緭鍏ュ弬鏁般€?            {"name": "claim_task",  # 瀹氫箟浠诲姟璁ら宸ュ叿銆?             "description": "璁ら涓€涓緟澶勭悊浠诲姟銆?,  # 璇存槑宸ュ叿鐢ㄩ€斻€?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {"task_id": {"type": "string"}},  # 瀹氫箟浠诲姟 ID 鍙傛暟銆?                              "required": ["task_id"]}},  # 浠诲姟 ID 蹇呭～銆?            {"name": "complete_task",  # 瀹氫箟浠诲姟瀹屾垚宸ュ叿銆?             "description": "灏嗕竴涓繘琛屼腑鐨勪换鍔℃爣璁颁负宸插畬鎴愩€?,  # 璇存槑宸ュ叿鐢ㄩ€斻€?             "input_schema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                              "properties": {"task_id": {"type": "string"}},  # 瀹氫箟浠诲姟 ID 鍙傛暟銆?                              "required": ["task_id"]}},  # 浠诲姟 ID 蹇呭～銆?        ]  # 缁撴潫闃熷弸宸ュ叿瀹氫箟鍒楄〃銆?
        sub_handlers = {  # schema 涓庡鐞嗗櫒鍒嗙锛氭ā鍨嬬湅鍒扮粺涓€宸ュ叿鍚嶏紝杩愯鏃跺湪姝ゆ敞鍏ラ槦鍙嬭韩浠藉拰浠诲姟 cwd銆?            "bash": _run_bash, "read_file": _run_read,  # 缁戝畾闃熷弸浣滅敤鍩熺殑 Shell 鍜岃鍙栧鐞嗗櫒銆?            "write_file": _run_write, "edit_file": _run_edit,  # 缁戝畾鍐欏叆鍜岀紪杈戝鐞嗗櫒銆?            "glob": _run_glob,  # 缁戝畾鏂囦欢鎼滅储澶勭悊鍣ㄣ€俖teammate_send_message
            "send_message": lambda to, content: _teammate_send_message(  # 闂寘鍥哄畾鍙戦€佽€咃紝妯″瀷涓嶈兘浼€?from 瀛楁銆?                name, to, content),  # 灏嗛槦鍙嬪悕绉颁綔涓烘秷鎭彂閫佹柟銆?            "submit_plan": lambda plan: _teammate_submit_plan(name, plan),  # 鍚屾牱缁戝畾闃熷弸韬唤锛屼娇瀹℃壒鐘舵€佷笌姝ｇ‘绾跨▼鍏宠仈銆?            "list_tasks": _run_list_tasks,  # 缁戝畾浠诲姟鍒楄〃澶勭悊鍣ㄣ€?            "claim_task": _run_claim_task,  # 缁戝畾浠诲姟棰嗗彇澶勭悊鍣ㄣ€?            "complete_task": _run_complete_task,  # 缁戝畾浠诲姟瀹屾垚澶勭悊鍣ㄣ€?        }  # 缁撴潫宸ュ叿澶勭悊鍣ㄦ槧灏勩€?
        should_stop = False  # 鍏抽棴鍙兘鐢卞凡楠岃瘉鍗忚娑堟伅鎴栦笉鍙仮澶嶅紓甯歌Е鍙戯紝鏅€氭ā鍨嬪畬鎴愪笉浼氶攢姣佺嚎绋嬨€?        while not should_stop:  # 澶栧眰寰幆浠ｈ〃闃熷弸鐢熷懡鍛ㄦ湡锛屽彲璺ㄨ秺澶氫釜浠诲姟鍜屽娆℃ā鍨嬭皟鐢ㄣ€?            for msg in BUS.read_inbox(name):  # 姣忔璋冪敤妯″瀷鍓嶅厛澶勭悊鎺у埗娑堟伅锛岄伩鍏嶅叧闂垨瀹℃壒鍝嶅簲琚欢杩熶竴杞€?                if handle_inbox_message(name, msg, messages):  # 浠呭凡纭鐨?shutdown_request 杩斿洖 True銆?                    should_stop = True  # 璁板綍閫€鍑烘剰鍥撅紝璁╁祵濂楀惊鐜叡浜悓涓€缁堟鐘舵€併€?                    break  # 鍋滄娑堣垂褰撳墠鎵规锛屽墿浣欐竻鐞嗙敱绾跨▼鍑哄彛璐熻矗銆?            if should_stop:  # 閬垮厤鏀跺埌鍏抽棴鍚庝粛鍙戣捣涓€娆℃槀璐典笖鍙兘鍐欐枃浠剁殑妯″瀷璋冪敤銆?                break  # 璺冲埌 run() 鐨?finally 鎵ц浠诲姟閲婃斁鍜屾敞鍐岃〃娓呯悊銆?            with team_lock:  # 鐘舵€佷細琚?Lead 鐨?list_teammates 骞跺彂璇诲彇锛屽洜姝ゅ啓鍏ラ渶涓庡洟闃熼攣鍚屾銆?                active_teammates[name] = "working"  # 琛ㄧず褰撳墠鍗冲皢鎬濊€冩垨鎵ц宸ュ叿锛岃€岄潪绛夊緟鏂板伐浣溿€?            try:  # 鍗曟妯″瀷鏁呴殰鍙粨鏉熻闃熷弸锛岀敱 Lead 鏀跺埌 error 鍚庡喅瀹氭槸鍚﹂噸娲俱€?                response = client.messages.create(  # 璋冪敤妯″瀷澶勭悊闃熷弸褰撳墠鍘嗗彶銆?                    model=MODEL, system=system, messages=messages,  # 浼犲叆妯″瀷銆侀槦鍙嬬郴缁熸彁绀鸿瘝鍜屽巻鍙层€?                    tools=sub_tools, max_tokens=8000)  # 闃熷弸鍏变韩涓绘ā鍨嬶紝浣嗘秷鎭€佸伐鍏锋潈闄愬拰鐘舵€佸畬鍏ㄧ嫭绔嬨€?            except Exception as exc:  # 鎹曡幏缃戠粶銆侀壌鏉冨強鏈嶅姟閿欒锛岄槻姝㈠悗鍙扮嚎绋嬮潤榛樻浜°€?                BUS.send(name, "lead",  # 灏嗘ā鍨嬭皟鐢ㄥ紓甯稿彂閫佺粰 Lead銆?                         f"{type(exc).__name__}: {exc}", "error")  # 鎶婃晠闅滈€佸洖 Lead 鐨勭粺涓€浜嬩欢閫氶亾銆?                break  # 褰撳墠闃熷弸缂哄皯绗?15 绔犱富寰幆鐨勯噸璇曠姸鎬侊紝浜ょ敱鍗忚皟鑰呴噸鏂板喅绛栨洿瀹夊叏銆?            messages.append({"role": "assistant", "content": response.content})  # 鍏堜繚瀛樺畬鏁村搷搴旓紝淇濊瘉鍚庣画 tool_result 閰嶅鍚堟硶銆?            tool_calls = [  # 涓嶄緷璧?stop_reason锛岃€屼互瀹為檯 tool_use 鍧楀喅瀹氭槸鍚︾户缁伐鍏峰弽棣堝惊鐜€?                block for block in response.content if block.type == "tool_use"  # 绛涢€夊搷搴斾腑鐨勫疄闄呭伐鍏疯皟鐢ㄣ€?            ]  # 缁撴潫宸ュ叿璋冪敤鍒楄〃銆?            if tool_calls:  # 鍚屼竴鍝嶅簲鍙兘璇锋眰澶氫釜宸ュ叿锛岄渶鍏ㄩ儴鎵ц鍚庝竴娆℃€у洖浼犵粨鏋溿€?                results = []  # 姣忎釜缁撴灉鐢?tool_use_id 涓庡師璋冪敤绮剧‘鍏宠仈銆?                for block in tool_calls:  # 淇濇寔妯″瀷缁欏嚭鐨勯『搴忥紝闄嶄綆瀛樺湪闅愬惈鍏堝悗渚濊禆鏃剁殑鎰忓琛屼负銆?                    output = _run_teammate_tool(name, block, sub_handlers)  # 涓ぎ鍒嗗彂鍣ㄥ悓鏃舵墽琛岃鍒掗棬绂佸拰澶勭悊鍣ㄦ煡鎵俱€?                    results.append({"type": "tool_result",  # 鏋勯€犲伐鍏风粨鏋滄秷鎭€?                                    "tool_use_id": block.id,  # 鍏宠仈鍘熷伐鍏疯皟鐢?ID銆?                                    "content": str(output)})  # 缁熶竴杞垚鏂囨湰锛岄伩鍏嶅鐞嗗櫒杩斿洖绫诲瀷鐮村潖娑堟伅鍗忚銆?                messages.append({"role": "user", "content": results})  # 宸ュ叿缁撴灉浣滀负鐢ㄦ埛渚у唴瀹瑰弽棣堢粰鍚屼竴闃熷弸妯″瀷銆?                continue  # 鏈夊伐鍏疯皟鐢ㄨ鏄庝换鍔″皻鏈舰鎴愭渶缁堢瓟澶嶏紝绔嬪嵆杩涘叆涓嬩竴妯″瀷杞銆?
            summary = _last_assistant_text(response.content)  # 鏃犲伐鍏疯皟鐢ㄦ椂锛屾妸鏈€鍚庢枃鏈涓洪樁娈电粨鏋滄垨宸叉彁浜よ鍒掑悗鐨勮鏄庛€?            gate = plan_gates.get(name, "not_required")  # 璇诲彇璁″垝鐘舵€侊紝鍖哄垎鐪熸瀹屾垚涓庣瓑寰?Lead 瀹℃壒銆?            if gate != "pending" and summary:  # 寰呭鎵规枃鏈凡鐢?submit_plan 鍗忚鍙戦€侊紝涓嶈兘鍐嶄吉瑁呮垚鏈€缁堢粨鏋溿€?                BUS.send(name, "lead", summary, "result")  # 姝ｅ父闃舵缁撴灉閫氳繃閭浜ょ粰 Lead锛岃€屼笉鏄洿鎺ユ墦鍗板埌鍏变韩缁堢銆?            if gate == "pending":  # 鎻愪氦璁″垝鍚庡繀椤讳繚鐣欏綋鍓嶄换鍔″強鐩綍锛岀瓑寰呭悓涓€宸ヤ綔韬唤缁х画鎵ц銆?                with team_lock:  # Lead 鍙兘鍚屾椂鏌ヨ闃熷弸鐘舵€併€?                    active_teammates[name] = "waiting_approval"  # 鐘舵€佹槑纭樉绀洪樆濉炲師鍥狅紝涓嶄細琚鍒や负绌洪棽鍙垎閰嶃€?            else:  # 鏈瓑寰呭鎵规剰鍛崇潃鏈疆宸ヤ綔宸茶嚜鐒剁粨鏉燂紝鍙繘鍏ヤ换鍔℃帴缁樁娈点€?                release_completed_assignment(name)  # 浠呭凡瀹屾垚浠诲姟浼氶噴鏀?cwd 绉熺害锛涙湭瀹屾垚浠诲姟浠嶄繚鎸佺粦瀹氥€?                with team_lock:  # 鍘熷瓙鍙戝竷绌洪棽鐘舵€侊紝渚涘崗璋冪晫闈㈣鍙栥€?                    active_teammates[name] = "idle"  # 绾跨▼浠嶅瓨娲伙紝鍙槸鏆傛椂娌℃湁妯″瀷宸ヤ綔銆?                BUS.send(name, "lead", "Waiting for more work.",  # 鍚?Lead 鍙戦€佺┖闂查€氱煡銆?                         "idle_notification")  # 涓诲姩閫氱煡 Lead锛屾棤闇€鍏惰疆璇㈢嚎绋嬬姸鎬併€?
            while True:  # 绌洪棽寰幆鍚屾椂绛夊緟鍗忚娑堟伅锛屽苟鍛ㄦ湡鎬у皾璇曚粠鍏变韩浠诲姟鏉挎帴娲汇€?                inbox = BUS.wait_for_messages(name, IDLE_SCAN_INTERVAL)  # 鏉′欢绛夊緟鍑忓皯蹇欒疆璇紝鍚屾椂鐢ㄨ秴鏃朵繚鐣欎换鍔℃壂鎻忔満浼氥€?                if inbox:  # 娑堟伅浼樺厛浜庤嚜鍔ㄨ棰嗭紝纭繚鍏抽棴鎴?Lead 鎸囦护鑳藉強鏃剁敓鏁堛€?                    for msg in inbox:  # 涓€娆″鐞嗛偖绠变腑宸插埌杈剧殑鍏ㄩ儴娑堟伅銆?                        if handle_inbox_message(name, msg, messages):  # 鍏抽棴鍝嶅簲浼氳缃粺涓€閫€鍑烘爣蹇椼€?                            should_stop = True  # 灏嗗唴灞傛帶鍒剁粨鏋滀紶鍥炲灞傜敓鍛藉懆鏈熷惊鐜€?                            break  # 涓嶅啀澶勭悊鍏抽棴涔嬪悗鐨勬櫘閫氭秷鎭€?                    if should_stop or messages[-1]["role"] == "user":  # 鏂扮敤鎴锋秷鎭剰鍛崇潃妯″瀷宸叉湁涓嬩竴杞緭鍏ャ€?                        break  # 杩斿洖澶栧眰寰幆锛岃娑堟伅缁忚繃姝ｅ父妯″瀷璋冪敤澶勭悊銆?                    continue  # 鍙湁鍐呴儴鍗忚娑堟伅涓旀湭浜х敓妯″瀷杈撳叆鏃剁户缁瓑寰呫€?
                task = claim_next_task(name)  # 瓒呮椂鍚庡師瀛愬皾璇曡棰嗛涓緷璧栨弧瓒充笖鐩綍鍙敤鐨勪换鍔°€?                if not task:  # 娌℃湁鍙墽琛屼换鍔℃槸姝ｅ父绌洪棽鐘舵€侊紝涓嶅簲閫€鍑洪暱鏈熼槦鍙嬬嚎绋嬨€?                    continue  # 缁х画绛夊緟娑堟伅鎴栦笅涓€娆′换鍔℃壂鎻忋€?                try:  # 璁ら鍚庤В鏋愮粦瀹氱洰褰曪紝鐢ㄤ簬鍚戞ā鍨嬫槑纭疄闄呮墽琛屼綅缃€?                    workdir = str(assignment_cwd(name))  # 宸ヤ綔鏍戜换鍔″緱鍒伴殧绂荤洰褰曪紝鏅€氫换鍔″緱鍒颁富宸ヤ綔鍖恒€?                except (FileNotFoundError, ValueError) as exc:  # 闃插尽璁ら鍚庣洰褰曡澶栭儴鐮村潖鐨勭獎绔炰簤绐楀彛銆?                    workdir = f"unavailable ({exc})"  # 灏嗛棶棰樺啓杩涙彁绀猴紝鍚庣画宸ュ叿浠嶄細 fail-closed銆?                messages.append({  # 鎶婃柊璁ら浠诲姟鍔犲叆闃熷弸鍘嗗彶銆?                    "role": "user",  # 浠ョ敤鎴蜂晶娑堟伅鎻愪緵鏂板伐浣溿€?                    "content": (  # 鑷姩浠诲姟浣滀负鏂扮殑鐢ㄦ埛鎸囦护杩藉姞锛屼繚鐣欓槦鍙嬫鍓嶇Н绱殑鍗忎綔涓婁笅鏂囥€?                        f"[鑷姩璁ら浠诲姟 {task.id}] "  # 娉ㄦ槑鑷姩璁ら鐨勪换鍔?ID銆?                        f"{task.subject}\n{task.description}\n"  # 闄勪笂浠诲姟涓婚涓庢弿杩般€?                        f"宸ヤ綔鐩綍锛歿workdir}"  # 闄勪笂浠诲姟宸ヤ綔鐩綍銆?                    ),  # 缁撴潫浠诲姟璇存槑鏂囨湰銆?                })  # 瀹屾垚娑堟伅杩藉姞銆?                print(f"  \033[32m[idle] {name} claimed "  # 杈撳嚭鑷姩棰嗗彇鏃ュ織銆?                      f"{task.id}: {task.subject}\033[0m")  # 闄勪笂浠诲姟缂栧彿涓庝富棰樸€?                break  # 宸茶幏寰楁柊宸ヤ綔锛岄€€鍑虹┖闂插惊鐜苟鍥炲埌妯″瀷璋冪敤闃舵銆?
    def run():  # 鍚姩骞舵竻鐞嗛槦鍙嬬嚎绋嬭繍琛屾椂锛涙渶鏃╋細15.1623 鈭?        try:  # 鐢ㄦ渶澶栧眰淇濇姢澹冲寘浣忓畬鏁寸敓鍛藉懆鏈燂紝纭繚浠讳綍鍐呴儴閬楁紡寮傚父閮借繘鍏ョ粺涓€娓呯悊璺緞銆?            run_loop()  # 姝ｅ父鎯呭喌涓嬭鍑芥暟浼氭寔缁法浠诲姟杩愯锛岀洿鍒版敹鍒板悎娉曞叧闂姹傛垨妯″瀷璋冪敤澶辫触銆?        except Exception as exc:  # 鎹曡幏宸ュ叿銆佸崗璁拰鐘舵€佷唬鐮佷腑鏈鏈熺殑寮傚父锛岄伩鍏嶅悗鍙扮嚎绋嬫棤澹伴€€鍑恒€?            try:  # 閿欒涓婃姤鏈韩渚濊禆閭鏂囦欢锛屽洜姝や篃蹇呴』鍗曠嫭闃叉姢銆?                BUS.send(name, "lead", f"{type(exc).__name__}: {exc}", "error")  # 璁?Lead 鑾峰緱鍙瀵熺殑澶辫触浜嬩欢銆?            except Exception:  # 閭涓嶅彲鍐欐椂宸叉棤鍙潬涓婃姤閫氶亾銆?                pass  # 淇濈暀 finally 娓呯悊浼樺厛绾э紝涓嶇敤娆＄敓寮傚父瑕嗙洊鍘熷鏁呴殰銆?        finally:  # 鏃犺姝ｅ父鍏抽棴杩樻槸寮傚父閫€鍑猴紝閮藉繀椤昏В闄ゆ寔涔呬换鍔′笌鍐呭瓨娉ㄥ唽鐘舵€併€?            try:  # 閲婃斁鍙兘娑夊強浠诲姟鏂囦欢閿佸拰纾佺洏鍐欏叆锛屽洜姝や笉鑳藉亣璁惧繀鐒舵垚鍔熴€?                release_teammate_assignment(name)  # 鏈畬鎴愪换鍔￠€€鍥?pending锛岄伩鍏嶇嚎绋嬫浜″悗褰㈡垚姘镐箙鍗犵敤銆?            except Exception as exc:  # 娓呯悊澶辫触浼氬奖鍝嶅悗缁皟搴︼紝灏介噺鍚?Lead 鍙戝嚭楂樹紭鍏堢骇閿欒銆?                try:  # 閭寮傚父浠嶄笉鑳介樆姝㈠叾浣欏唴瀛樼姸鎬佹竻鐞嗐€?                    BUS.send(  # 鍚?Lead 鍙戦€佹竻鐞嗗け璐ヤ俊鎭€?                        name, "lead",  # 鎸囧畾鍙戦€佹柟鍜屾帴鏀舵柟銆?                        f"Assignment cleanup failed: {type(exc).__name__}: {exc}",  # 闄勪笂寮傚父绫诲瀷鍜屽唴瀹广€?                        "error",  # 鏄庣‘鏍囦负閿欒浜嬩欢锛屽尯鍒簬闃熷弸鐨勬櫘閫氱粨鏋滄枃鏈€?                    )  # 缁撴潫閿欒娑堟伅鍙戦€併€?                except Exception:  # 娌℃湁鏇村瀹夊叏鎭㈠鎵嬫鏃跺悶鎺変笂鎶ュ紓甯革紝缁х画娓呭唴瀛樻敞鍐岃〃銆?                    pass  # 蹇界暐涓婃姤寮傚父骞剁户缁竻鐞嗐€?            with team_lock:  # 涓夊紶琛ㄥ叡鍚屾弿杩板悓涓€闃熷弸锛屽繀椤诲湪鍚屼竴涓寸晫鍖哄唴绉婚櫎銆?                active_teammates.pop(name, None)  # 浠庡彲瀵诲潃闃熷弸闆嗗悎绉婚櫎锛屽悗缁秷鎭彂閫佸皢琚嫆缁濄€?                plan_gates.pop(name, None)  # 娓呴櫎璁″垝闂ㄧ锛岄伩鍏嶅悓鍚嶉槦鍙嬮噸寤烘椂缁ф壙鏃х姸鎬併€?                plan_request_ids.pop(name, None)  # 娓呴櫎鍏宠仈璇锋眰 ID锛屼娇杩熷埌瀹℃壒鏃犳硶鍛戒腑鏂扮嚎绋嬨€?            print(f"  \033[32m[teammate] {name} finished\033[0m")  # 杈撳嚭鏈€缁堢敓鍛藉懆鏈熶簨浠讹紝渚夸簬鏈湴瑙傚療銆?
    threading.Thread(target=run, daemon=True).start()  # 瀹堟姢绾跨▼涓嶉樆姝?CLI 閫€鍑猴紝璧勬簮涓€鑷存€х敱 run() 鐨?finally 缁存姢銆?    print(f"  \033[36m[teammate] {name} spawned as {role}\033[0m")  # 绔嬪嵆鏄剧ず鍒涘缓鎴愬姛锛屼笉绛夊緟闃熷弸瀹屾垚棣栬疆妯″瀷璋冪敤銆?    assigned = f" for {task_id}" if task_id else " without an initial Task"  # 杩斿洖鍊煎尯鍒嗛鍒嗛厤涓庣┖闂插惎鍔紝鏂逛究 Lead 鏍￠獙鎰忓浘銆?    return (  # 鏋勯€犲惎鍔ㄧ粨鏋滄彁绀恒€?        f"Teammate '{name}' spawned as {role}{assigned}. "  # 璇存槑闃熷弸瑙掕壊鍙婂垵濮嬩换鍔°€?        "End this turn; the runtime will deliver its events."  # 寮哄埗浜嬩欢椹卞姩鍗忎綔锛岄伩鍏?Lead 蹇欒疆璇㈡氮璐逛笂涓嬫枃鍜岃皟鐢ㄩ搴︺€?    )  # 缁撴潫鍚姩缁撴灉銆?

def _teammate_submit_plan(from_name: str, plan: str) -> str:  # 鎻愪氦闃熷弸璁″垝骞剁瓑寰?Lead 瀹℃壒锛涙渶鏃╋細13.1008 鈭?    with task_lock:  # 鎸侀攣璇诲彇褰撳墠浠诲姟鍒嗛厤銆?        assignment = teammate_assignments.get(from_name)  # 鏌ユ壘鎻愪氦鑰呯殑浠诲姟蹇収銆?        task_id = str(assignment["task_id"]) if assignment else None  # 鎻愬彇褰撳墠浠诲姟 ID锛屽彲鑳戒负绌恒€?        work_version = assignment_versions.get(from_name, 0)  # 璇诲彇褰撳墠鍒嗛厤鐗堟湰銆?        with team_lock:  # 鎸侀攣鏇存柊鍥㈤槦鍗忚鐘舵€併€?            if plan_gates.get(from_name) == "pending":  # 宸叉湁寰呭鎵硅鍒掓椂涓嶉噸澶嶆彁浜ゃ€?                return "A plan is already waiting for review."  # 鎻愮ず绛夊緟宸叉湁瀹℃壒銆?            req_id = new_request_id()  # 鐢熸垚鏂扮殑鍗忚璇锋眰缂栧彿銆?            pending_requests[req_id] = ProtocolState(  # 鍒涘缓璁″垝瀹℃壒璇锋眰璁板綍銆?                request_id=req_id, type="plan_approval",  # 淇濆瓨璇锋眰缂栧彿鍜岀被鍨嬨€?                sender=from_name, target="lead",  # 璁板綍鎻愪氦鏂瑰強瀹℃壒鏂广€?                status="pending", payload=plan,  # 璁板綍寰呭鎵圭姸鎬佸拰璁″垝鍐呭銆?                work_version=work_version, task_id=task_id)  # 缁戝畾褰撳墠浠诲姟鍙婂垎閰嶇増鏈€?            plan_gates[from_name] = "pending"  # 灏嗚鍒掗棬鎺ц涓哄緟瀹℃壒銆?            plan_request_ids[from_name] = req_id  # 淇濆瓨褰撳墠璁″垝璇锋眰缂栧彿銆?            active_teammates[from_name] = "waiting_approval"  # 灏嗛槦鍙嬬姸鎬佽涓虹瓑寰呭鎵广€?    BUS.send(from_name, "lead", plan,  # 閫氳繃閭鍚?Lead 鍙戦€佽鍒掋€?             "plan_approval_request",  # 鎸囧畾璁″垝瀹℃壒璇锋眰绫诲瀷銆?             {"request_id": req_id})  # 鍦ㄥ厓鏁版嵁涓檮涓婅姹傜紪鍙枫€?    return f"Plan submitted ({req_id}). Wait for Lead's decision."  # 杩斿洖鎻愪氦缁撴灉骞舵彁绀虹瓑寰呫€?

# -- Lead Team Tools --锝滀富 Agent 鍥㈤槦宸ュ叿锛氱户鎵跨 13 绔狅紝鐢?Lead 绠＄悊璁″垝銆佹秷鎭笌闃熷弸鐢熷懡鍛ㄦ湡銆?
def run_request_shutdown(teammate: str) -> str:  # 鍚戞寚瀹氶槦鍙嬪彂閫佸叧闂姹傦紱鏈€鏃╋細13.1448 鈭?    if teammate not in active_teammates:
        return f"Teammate '{teammate}' is not active"
    with team_lock:
        req_id = new_request_id()
        pending_requests[req_id] = ProtocolState(
            request_id=req_id, type="shutdown",
            sender="lead", target=teammate,
            status="pending", payload="")
    BUS.send("lead", teammate, "Finish the current step and shut down.",
             "shutdown_request",
             {"request_id": req_id})
    print(f"  \033[35m[protocol] shutdown_request -> {teammate} "
          f"({req_id})\033[0m")
    return f"Shutdown requested from {teammate} ({req_id})"


def run_request_plan(teammate: str, task: str) -> str:  # 瑕佹眰鎸囧畾闃熷弸鍏堟彁浜ゆ墽琛岃鍒掞紱鏈€鏃╋細13.1466 鈭?    if teammate not in active_teammates:
        return f"Teammate '{teammate}' is not active"
    with team_lock:
        plan_gates[teammate] = "required"
    BUS.send("lead", teammate, task, "plan_request")
    return f"Plan requested from {teammate}"


def run_review_plan(request_id: str, approve: bool,  # 瀹℃壒鎴栨嫆缁濋槦鍙嬭鍒掞紱鏈€鏃╋細13.1475 鈭?                    feedback: str = "") -> str:
    state = pending_requests.get(request_id)
    if not state:
        return f"Request {request_id} not found"
    work_version, task_id = current_work_identity(state.sender)
    with team_lock:
        state = pending_requests.get(request_id)
        if not state:
            return f"Request {request_id} not found"
        if state.type != "plan_approval":
            return f"Request {request_id} is not a plan"
        if state.status != "pending":
            return f"Request {request_id} already {state.status}"
        if state.work_version != work_version or state.task_id != task_id:
            return f"Request {request_id} belongs to an earlier assignment"
        if plan_request_ids.get(state.sender) != request_id:
            return f"Request {request_id} is not the current plan"
        state.status = "approved" if approve else "rejected"
    content = feedback or ("Plan approved." if approve
                           else "Revise the plan and submit it again.")
    BUS.send("lead", state.sender, content,
             "plan_approval_response",
             {"request_id": request_id, "approve": approve})
    icon = "approved" if approve else "rejected"
    print(f"  \033[32m[protocol] plan {icon} ({request_id})\033[0m")
    return f"Plan {state.status} ({request_id})"


# -- Hooks and Permission Checks --锝滈挬瀛愪笌鏉冮檺锛氭部鐢ㄧ 3 绔犳潈闄愯鍒欙紝骞堕噰鐢ㄧ 4 绔犵殑鐢熷懡鍛ㄦ湡閽╁瓙鏋舵瀯銆?
# Hooks are intentionally outside tool handlers. The loop can add permission,锝滀腑鏂囷細閽╁瓙鍒绘剰缃簬宸ュ叿澶勭悊鍣ㄤ箣澶栵紝浣垮惊鐜彲浠ュ鍔犳潈闄愭帶鍒躲€?# logging, and stop behavior without changing each individual tool.锝滀腑鏂囷細鏃ュ織鍜屽仠姝㈣涓猴紝鑰屾棤闇€閫愪釜淇敼宸ュ叿銆?HOOKS = {"UserPromptSubmit": [], "PreToolUse": [],
         "PostToolUse": [], "Stop": []}


def register_hook(event: str, callback):  # 缁欐寚瀹氱敓鍛藉懆鏈熶簨浠舵敞鍐岄挬瀛愶紱鏈€鏃╋細04.130 鈭?    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):  # 渚濇鎵ц鎸囧畾浜嬩欢鐨勫叏閮ㄩ挬瀛愶紱鏈€鏃╋細04.133 鈭?    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
mcp_tool_policies: dict[str, str] = {}


def permission_hook(block):  # 鍦ㄥ伐鍏锋墽琛屽墠鎷︽埅鍗遍櫓鎴栬秺鐣屾搷浣滐紱鏈€鏃╋細04.153 鈭?    # The permission layer sees the raw tool_use before dispatch. It can deny,锝滀腑鏂囷細鏉冮檺灞傚湪鍒嗗彂鍓嶈鍙栧師濮?tool_use锛屽彲鐩存帴鎷掔粷銆?    # ask the user, or allow execution to continue.锝滀腑鏂囷細璇㈤棶鐢ㄦ埛锛屾垨鍏佽缁х画鎵ц銆?    if block.name == "bash":
        command = block.input.get("command", "")
        if not isinstance(command, str):
            return "Permission denied: shell command must be a string"
        for pattern in DENY_LIST:
            if pattern in command:
                return f"Permission denied: '{pattern}' is on the deny list"
        if threading.current_thread() is not threading.main_thread():
            return ("Permission denied: interactive shell approval is unavailable "
                    "during an asynchronous turn")
        terminal_print("\n\033[33m[permission] shell command\033[0m")
        terminal_print(f"  {command}")
        choice = CONSOLE.ask("  Allow? [y/N] ").strip().lower()
        if choice not in ("y", "yes"):
            return "Permission denied by user"
    if block.name in ("read_file", "write_file", "edit_file"):
        path = block.input.get("path", "")
        if not isinstance(path, str):
            return "Permission denied: path must be a string"
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            return "Permission denied: path is outside the workspace"
    if (block.name.startswith("mcp__")
            and mcp_tool_policies.get(block.name, "confirm") != "allow"):
        if threading.current_thread() is not threading.main_thread():
            return ("Permission denied: interactive MCP approval is unavailable "
                    "during an asynchronous turn")
        terminal_print(f"\n\033[33m[permission] MCP tool: {block.name}\033[0m")
        choice = CONSOLE.ask("  Allow? [y/N] ").strip().lower()
        if choice not in ("y", "yes"):
            return "Permission denied by user"
    return None


def log_hook(block):  # 璁板綍姣忔宸ュ叿璋冪敤鎽樿锛涙渶鏃╋細04.180 鈭?    print(f"\033[90m[HOOK] {block.name}\033[0m")
    return None


def large_output_hook(block, output):  # 鎻愮ず宸ュ叿杈撳嚭鏄惁闇€瑕佽惤鐩橈紱鏈€鏃╋細04.187 鈭?    if len(str(output)) > 100000:
        print(f"\033[33m[HOOK] large output from {block.name}: "
              f"{len(str(output))} chars\033[0m")
    return None


def user_prompt_hook(query: str):  # 璁板綍鐢ㄦ埛璇锋眰瀵瑰簲鐨勫伐浣滅洰褰曪紱鏈€鏃╋細15.1810 鈭?    print(f"\033[90m[HOOK] UserPromptSubmit: {WORKDIR}\033[0m")
    return None


def stop_hook(messages: list):  # 缁熻浼氳瘽宸ュ叿璋冪敤骞跺鐞嗗仠姝㈣竟鐣岋紱鏈€鏃╋細15.1815 鈭?    tool_count = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            tool_count += sum(1 for item in content
                              if isinstance(item, dict)
                              and item.get("type") == "tool_result")
    print(f"\033[90m[HOOK] Stop: {tool_count} tool result(s)\033[0m")
    return None


register_hook("UserPromptSubmit", user_prompt_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", stop_hook)


# -- Subagent Tool --锝滃瓙 Agent 宸ュ叿锛氱户鎵跨 6 绔狅紝鐢ㄥ叏鏂版秷鎭笂涓嬫枃鎵ц涓€娆℃€у娲句换鍔°€?
SUB_SYSTEM = (
    f"浣犳槸鍦?{WORKDIR} 涓伐浣滅殑缂栫▼瀛?Agent銆?
    "璇峰畬鎴愪换鍔★紝鐒跺悗杩斿洖绠€娲佺殑鏈€缁堟€荤粨銆?
    "涓嶈缁х画鐢熸垚鍏朵粬 Agent銆?
)


SUB_TOOLS = [
    {"name": "bash", "description": "杩愯涓€鏉?Shell 鍛戒护銆?,
     "input_schema": {"type": "object",
                      "properties": {"command": {"type": "string"}},
                      "required": ["command"]}},
    {"name": "read_file", "description": "璇诲彇鏂囦欢鍐呭銆?,
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "limit": {"type": "integer"},
                                     "offset": {"type": "integer"}},
                      "required": ["path"]}},
    {"name": "write_file", "description": "鎶婂唴瀹瑰啓鍏ユ枃浠躲€?,
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "description": "鍦ㄦ枃浠朵腑绮剧‘鏇挎崲涓€娆℃寚瀹氭枃鏈€?,
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "old_text": {"type": "string"},
                                     "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "鏌ユ壘绗﹀悎 glob 妯″紡鐨勬枃浠讹紱** 琛ㄧず閫掑綊鍖归厤銆?,
     "input_schema": {"type": "object",
                      "properties": {"pattern": {"type": "string"}},
                      "required": ["pattern"]}},
]


SUB_HANDLERS = {
    "bash": run_bash, "read_file": run_read,
    "write_file": run_write, "edit_file": run_edit,
    "glob": run_glob,
}


def extract_text(content) -> str:  # 鎻愬彇妯″瀷鍝嶅簲涓殑鏂囨湰鍧楋紱鏈€鏃╋細06.260  鈭?    if not isinstance(content, list):
        return str(content)
    return "\n".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", None) == "text").strip()


def has_tool_use(content) -> bool:  # 鍒ゆ柇鍝嶅簲鏄惁鍖呭惈宸ュ叿璋冪敤锛涙渶鏃╋細15.1888 鈭?    # Do not rely on stop_reason alone; the concrete tool_use block is the锝滀腑鏂囷細涓嶈兘鍙緷璧?stop_reason锛涘疄闄呭瓨鍦ㄧ殑 tool_use 鍐呭鍧楋紝
    # continuation signal used by the loop.锝滀腑鏂囷細鎵嶆槸寰幆缁х画鎵ц鐨勪俊鍙枫€?    return any(getattr(block, "type", None) == "tool_use"
               for block in content)


def spawn_subagent(description: str) -> str:  # 杩愯涓€娆″叿鏈夊叏鏂颁笂涓嬫枃鐨勫瓙 Agent锛涙渶鏃╋細15.1895 鈭?    messages = [{"role": "user", "content": description}]  # 浠ュ娲炬弿杩板垱寤虹嫭绔嬬殑瀛?Agent 娑堟伅鍘嗗彶銆?    for _ in range(30):  # 鏈€澶氳繘琛?30 娆℃ā鍨嬭皟鐢ㄣ€?        response = client.messages.create(  # 璋冪敤妯″瀷澶勭悊褰撳墠瀛愪换鍔°€?            model=MODEL, system=SUB_SYSTEM, messages=messages,  # 浣跨敤涓绘ā鍨嬨€佸瓙 Agent 鎻愮ず璇嶅拰鐙珛鍘嗗彶銆?            tools=SUB_TOOLS, max_tokens=8000)  # 鎻愪緵鍙楅檺宸ュ叿闆嗗拰杈撳嚭棰勭畻銆?        messages.append({"role": "assistant", "content": response.content})  # 灏嗗畬鏁村搷搴斿姞鍏ュ瓙 Agent 鍘嗗彶銆?        if not has_tool_use(response.content):  # 娌℃湁宸ュ叿璋冪敤鏃剁粨鏉熸墽琛屽惊鐜€?            break  # 閫€鍑烘ā鍨嬩笌宸ュ叿寰幆銆?        results = []  # 鏀堕泦鏈疆鍏ㄩ儴宸ュ叿缁撴灉銆?        for block in response.content:  # 鎸夊搷搴旈『搴忛亶鍘嗗唴瀹瑰潡銆?            if block.type != "tool_use":  # 璺宠繃鏂囨湰绛夐潪宸ュ叿璋冪敤鍧椼€?                continue  # 缁х画澶勭悊涓嬩竴涓唴瀹瑰潡銆?            blocked = trigger_hooks("PreToolUse", block)  # 鎵ц宸ュ叿鍓嶈Е鍙戞潈闄愮瓑閽╁瓙銆?            if blocked:  # 閽╁瓙杩斿洖鎷︽埅淇℃伅鏃躲€?                output = str(blocked)  # 灏嗘嫤鎴師鍥犱綔涓哄伐鍏风粨鏋溿€?            else:  # 鏈嫤鎴椂鎵ц宸ュ叿銆?                handler = SUB_HANDLERS.get(block.name)  # 鎸夊悕绉版煡鎵惧瓙 Agent 宸ュ叿澶勭悊鍣ㄣ€?                output = call_tool_handler(handler, block.input, block.name)  # 璋冪敤澶勭悊鍣ㄥ苟杞崲鎵ц寮傚父銆?                trigger_hooks("PostToolUse", block, output)  # 宸ュ叿鎵ц鍚庤Е鍙戝悗缃挬瀛愩€?            results.append({"type": "tool_result",  # 鏋勯€犱笌宸ュ叿璋冪敤閰嶅鐨勭粨鏋溿€?                            "tool_use_id": block.id,  # 浣跨敤鍘熷伐鍏疯皟鐢?ID銆?                            "content": str(output)})  # 灏嗘墽琛岀粨鏋滆浆涓烘枃鏈€?        messages.append({"role": "user", "content": results})  # 灏嗘湰杞粨鏋滀綔涓虹敤鎴锋秷鎭弽棣堢粰妯″瀷銆?    for msg in reversed(messages):  # 浠庢渶鏂版秷鎭紑濮嬫煡鎵炬枃鏈€荤粨銆?        if msg["role"] == "assistant":  # 鍙粠鍔╂墜娑堟伅鎻愬彇鏂囨湰銆?            text = extract_text(msg["content"])  # 鎻愬彇鍝嶅簲涓殑鏂囨湰鍧椼€?            if text:  # 瀛樺湪闈炵┖鏂囨湰鏃躲€?                return text  # 灏嗘枃鏈繑鍥炵粰涓?Agent銆?        return "瀛?Agent 宸茬粨鏉燂紝浣嗘病鏈夎繑鍥炴枃鏈€荤粨銆?  # 褰撳墠鏈€鏂版秷鎭湭杩斿洖鏂囨湰鏃剁珛鍗宠繑鍥為粯璁ゆ彁绀恒€?

# -- Context Compaction --锝滀笂涓嬫枃鍘嬬缉锛氱户鎵跨 8 绔狅紝骞跺湪绗?15 绔犲鍔犲垎灞傝鍓€佺粨鏋滆惤鐩樺拰绱ф€ユ仮澶嶃€?
# Compaction is layered: first shrink oversized tool results, then trim old锝滀腑鏂囷細鍘嬬缉鎸夊眰鎵ц锛氬厛缂╁噺杩囧ぇ鐨勫伐鍏风粨鏋滐紝鍐嶈鍓棫娑堟伅锛?# message ranges, and only call the model for a summary when the context is锝滀腑鏂囷細鍙湁涓婁笅鏂囦粛鐒惰繃澶э紝鎴栬€呮ā鍨嬫槑纭姹傚帇缂╂椂锛?# still too large or the model explicitly asks for compact.锝滀腑鏂囷細鎵嶈皟鐢ㄦā鍨嬬敓鎴愬巻鍙叉憳瑕併€?def estimate_size(messages: list) -> int:  # 浼扮畻娑堟伅鍘嗗彶鍗犵敤瀛楃鏁帮紱鏈€鏃╋細15.1932  鈭?    return len(json.dumps(messages, default=str))  # 鐢ㄧ粺涓€搴忓垪鍖栧悗鐨勫瓧绗︽暟杩戜技璇锋眰浣撶Н锛屾垚鏈繙浣庝簬姣忚疆绮剧‘鍒嗚瘝銆?
def block_type(block):  # 鍏煎璇诲彇瀛楀吀鎴?SDK 鍐呭鍧楃被鍨嬶紱鏈€鏃╋細15.1935 鈭?    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)  # 鍘嗗彶涓悓鏃跺瓨鍦ㄨ惤鐩樺瓧鍏稿拰 SDK 瀵硅薄锛屽帇缂╁眰蹇呴』鍏煎涓ょ褰㈡€併€?

def message_has_tool_use(message: dict) -> bool:  # 鍒ゆ柇娑堟伅鏄惁鍙戣捣宸ュ叿璋冪敤锛涙渶鏃╋細15.1939  鈭?    if message.get("role") != "assistant":  # tool_use 鍙兘鐢卞姪鎵嬪彂璧凤紝鍏堟寜瑙掕壊缂╁皬鍒ゆ柇鑼冨洿銆?        return False  # 鐢ㄦ埛娑堟伅鍗充娇鍚浉浼煎瓧鍏镐篃涓嶈兘琚綋鎴愮湡瀹炲伐鍏疯皟鐢ㄣ€?    content = message.get("content")  # 璇诲彇鍙兘鏄函鏂囨湰鎴栧唴瀹瑰潡鍒楄〃鐨勬秷鎭浇鑽枫€?    if not isinstance(content, list):  # 绾枃鏈搷搴斾笉瀛樺湪鍙厤瀵圭殑 tool_use 鍧椼€?        return False  # 閬垮厤閬嶅巻瀛楃涓插苟浜х敓浼尮閰嶃€?    return any(block_type(block) == "tool_use" for block in content)  # 鍙瀛樺湪涓€涓皟鐢紝瑁佸壀鏃跺氨蹇呴』淇濇姢鍏剁粨鏋滆竟鐣屻€?

def is_tool_result_message(message: dict) -> bool:  # 鍒ゆ柇娑堟伅鏄惁鍖呭惈宸ュ叿缁撴灉锛涙渶鏃╋細15.1948  鈭?    if message.get("role") != "user":  # Anthropic 鍗忚鎶?tool_result 浣滀负鐢ㄦ埛渚у唴瀹瑰弽棣堛€?        return False  # 鍔╂墜渚у悓鍚嶇粨鏋勪笉鏋勬垚鍚堟硶鍙嶉娑堟伅銆?    content = message.get("content")  # 宸ュ叿缁撴灉涓庢櫘閫氭枃鏈彲鑳藉叡浜悓涓€鍐呭鍧楀垪琛ㄣ€?    if not isinstance(content, list):  # 瀛楃涓茬敤鎴锋秷鎭笉闇€瑕佺淮鎶ゅ伐鍏烽厤瀵瑰叧绯汇€?        return False
    return any(isinstance(block, dict) and block.get("type") == "tool_result"
               for block in content)


def collect_tool_results(messages: list):  # 鏀堕泦娑堟伅涓殑鍏ㄩ儴宸ュ叿缁撴灉鍙婁綅缃紱鏈€鏃╋細15.1958  鈭?    found = []  # 鍚屾椂淇濆瓨娑堟伅绱㈠紩銆佸潡绱㈠紩鍜屽璞″紩鐢紝渚夸簬鍚庣画鍘熷湴鏇挎崲鑰屼笉鎵撲贡鍘嗗彶椤哄簭銆?    for mi, msg in enumerate(messages):  # 閬嶅巻鏁翠釜鍘嗗彶锛屾棦瑕嗙洊杩戞湡缁撴灉锛屼篃瑕嗙洊鍙兘鍗犵┖闂寸殑鏃х粨鏋溿€?        content = msg.get("content")  # 鎻愬墠鍙栧嚭杞借嵎锛屽噺灏戝悗缁噸澶嶈闂€?        if msg.get("role") != "user" or not isinstance(content, list):  # 鎺掗櫎鍔╂墜鍝嶅簲鍜屾櫘閫氭枃鏈姹傘€?            continue  # 杩欎簺娑堟伅涓嶆槸宸ュ叿鍙嶉锛屼笉鍙備笌缁撴灉鍘嬬缉銆?        for bi, block in enumerate(content):  # 涓€鏉＄敤鎴锋秷鎭彲鑳藉寘鍚涓苟琛屽伐鍏风粨鏋溿€?            if isinstance(block, dict) and block.get("type") == "tool_result":  # 鍙敹闆嗗凡鏍囧噯鍖栦负瀛楀吀鐨勭粨鏋滃潡銆?                found.append((mi, bi, block))  # 淇濈暀浣嶇疆鐢ㄤ簬鍒ゆ柇缁撴灉鏄惁宸茶妯″瀷娑堣垂銆?    return found  # 杩斿洖瀵硅薄寮曠敤锛岃皟鐢ㄦ柟淇敼 block 鍗充細鏇存柊鍘?messages銆?

def unseen_tool_result_positions(messages: list) -> set[tuple[int, int]]:  # 鎵惧嚭涓绘ā鍨嬪皻鏈湅鍒扮殑宸ュ叿缁撴灉锛涙渶鏃╋細15.1970  鈭?    """Return results added since the model's most recent response.锝滀腑鏂囷細杩斿洖妯″瀷鏈€杩戜竴娆″搷搴斿悗鏂板鐨勭粨鏋溿€?""
    last_assistant = next(  # 浠庡熬閮ㄥ鎵炬渶杩戜竴娆℃ā鍨嬪搷搴旓紝瀹冩瀯鎴愨€滄ā鍨嬪凡鐪嬪埌鍘嗗彶鈥濈殑杈圭晫銆?        (index for index in range(len(messages) - 1, -1, -1)
         if messages[index].get("role") == "assistant"),
        -1,  # 灏氭棤鍔╂墜鍝嶅簲鏃讹紝鎵€鏈夌敤鎴蜂晶宸ュ叿缁撴灉閮借涓烘湭娑堣垂銆?    )
    return {
        (message_index, block_index)
        for message_index in range(last_assistant + 1, len(messages))
        if messages[message_index].get("role") == "user"
        and isinstance(messages[message_index].get("content"), list)
        for block_index, block in enumerate(messages[message_index]["content"])
        if isinstance(block, dict) and block.get("type") == "tool_result"
    }


def persisted_output_path(output: str) -> str | None:  # 鏍￠獙骞舵彁鍙栧凡钀界洏宸ュ叿缁撴灉璺緞锛涙渶鏃╋細15.1987  鈭?    candidate = None  # 榛樿鎶婂唴瀹硅涓烘櫘閫氬伐鍏疯緭鍑猴紝鍙湁涓ユ牸鏍煎紡鍖归厤鍚庢墠淇′换鍏朵腑鐨勮矾寰勩€?    if output.startswith("<persisted-output>\n"):  # 璇嗗埆褰撳墠鐗堟湰鐢熸垚鐨勫甫棰勮鎸佷箙鍖栧寘瑁呫€?        candidate = next(
            (line.removeprefix("Full output: ") for line in output.splitlines()
             if line.startswith("Full output: ")),
            None,
        )
    prefix = "[Earlier tool result saved at "  # 鍚屾椂鍏煎 micro_compact 浣跨敤鐨勮交閲忓巻鍙插崰浣嶇銆?    if output.startswith(prefix) and output.endswith("]"):  # 涓ょ閮藉尮閰嶆墠鎻愬彇锛岄伩鍏嶆櫘閫氳緭鍑轰腑鐨勭浉浼兼枃鏈璇銆?        candidate = output.removeprefix(prefix).removesuffix("]")
    if not candidate:  # 鏈В鏋愬嚭璺緞璇存槑鍐呭灏氭湭钀界洏銆?        return None  # 璋冪敤鏂归殢鍚庡彲浠ュ垱寤烘柊鐨勬寔涔呭寲鏂囦欢銆?    path = Path(candidate)  # 杞负 Path 鍚庡啀鎵ц瑙勮寖鍖栬竟鐣屾鏌ャ€?    if (not path.resolve().is_relative_to(TOOL_RESULTS_DIR.resolve())
            or not path.is_file()):
        return None  # 璺緞瓒婄晫鎴栨枃浠跺凡涓嶅瓨鍦ㄦ椂鎷掔粷澶嶇敤锛屼笉鑳芥妸浠绘剰鏂囨湰璺緞鏆撮湶涓哄彲淇＄粨鏋溿€?    return str(path)  # 浠呰繑鍥炰綅浜庝笓鐢ㄧ粨鏋滅洰褰曚笖鐪熷疄瀛樺湪鐨勬枃浠躲€?

def save_output(tool_use_id: str, output: str) -> Path:  # 鎶婂畬鏁村伐鍏疯緭鍑轰繚瀛樺埌缁撴灉鐩綍锛涙渶鏃╋細15.2007  鈭?    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)  # 寤惰繜鍒涘缓鐩綍锛屾病鏈夊ぇ鍨嬭緭鍑烘椂涓嶆薄鏌撳伐浣滃尯銆?    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(tool_use_id))[:120] or "unknown"  # 娓呮礂妯″瀷鎻愪緵鐨?ID锛岄樆姝㈣矾寰勭┛瓒婂苟闄愬埗鏂囦欢鍚嶉暱搴︺€?    path = TOOL_RESULTS_DIR / f"{safe_id}.txt"  # 鐢?tool_use_id 寤虹珛缁撴灉涓庡師璋冪敤涔嬮棿鐨勫彲杩借釜鍏崇郴銆?    path.write_text(output, encoding="utf-8")  # 瀹屾暣鍐呭濮嬬粓淇濆瓨锛屽帇缂╁彧鏀瑰彉鍙戦€佺粰妯″瀷鐨勫壇鏈€?    return path  # 杩斿洖璺緞渚涢瑙堝寘瑁呭拰鍚庣画 read_file 鎭㈠浣跨敤銆?

def persisted_preview(tool_use_id: str, output: str,  # 杩斿洖瀹屾暣杈撳嚭璺緞鍜屾埅鏂瑙堬紱鏈€鏃╋細15.2015  鈭?                      preview_chars: int = 2000) -> str:
    saved_path = persisted_output_path(output)  # 鍏堟鏌ユ槸鍚﹀凡鎸佷箙鍖栵紝閬垮厤鍘嬬缉澶氳疆鍚庨噸澶嶅澹冲拰閲嶅鍐欑洏銆?    if saved_path:  # 宸叉湁鍙俊鏂囦欢鏃剁洿鎺ュ鐢ㄥ悓涓€浠藉畬鏁寸粨鏋溿€?        path = Path(saved_path)  # 淇濇寔杩斿洖鍖呰涓殑璺緞绋冲畾锛屼究浜庢ā鍨嬪悗缁鍙栥€?        try:  # 鏂囦欢鍙兘鍦ㄤ袱娆″帇缂╀箣闂磋鐢ㄦ埛娓呯悊锛屽洜姝よ鍙栦粛闇€瀹归敊銆?            with path.open(encoding="utf-8") as saved:
                preview = saved.read(preview_chars)
        except OSError:  # 鏂囦欢鐭殏涓嶅彲璇绘椂涓嶈涓婁笅鏂囧噯澶囨祦绋嬪け璐ャ€?            preview = output[:preview_chars]  # 鍥為€€灞曠ず褰撳墠鍖呰鏂囨湰鐨勪竴閮ㄥ垎锛岃嚦灏戜繚鐣欓敊璇嚎绱€?    else:  # 棣栨閬囧埌鍘熷澶у瀷缁撴灉鏃跺垱寤烘寔涔呭壇鏈€?        path = save_output(tool_use_id, output)  # 鍏堜繚璇佸畬鏁寸粨鏋滃彲鎭㈠锛屽啀鎴柇涓婁笅鏂囧壇鏈€?        preview = output[:preview_chars]  # 棰勮淇濈暀寮€澶达紝閫氬父鍖呭惈鍛戒护閿欒鎴栨枃浠舵牸寮忕瓑鍏抽敭璇婃柇淇℃伅銆?    return (f"<persisted-output>\nFull output: {path}\n"
            f"Preview:\n{preview}\n</persisted-output>")


def persist_large_output(tool_use_id: str, output: str) -> str:  # 灏嗚秴澶у伐鍏疯緭鍑轰繚瀛樺埌纾佺洏锛涙渶鏃╋細15.2032  鈭?    if len(output) <= PERSIST_THRESHOLD:  # 灏忕粨鏋滅洿鎺ヤ繚鐣欙紝钀界洏鍙嶈€屼細澧炲姞璺緞杩借釜鎴愭湰銆?        return output  # 涓嶅仛鏃犳敹鐩婅浆鎹紝缁存寔鍘熷宸ュ叿鍙嶉銆?    return persisted_preview(tool_use_id, output)  # 澶х粨鏋滄浛鎹负鈥滃畬鏁磋矾寰?+ 鏈夐檺棰勮鈥濄€?

def tool_result_budget(messages: list, max_bytes: int = 200_000) -> list:  # 闄愬埗鏈€鏂颁竴鎵瑰伐鍏风粨鏋滅殑涓婁笅鏂囦綋绉紱鏈€鏃╋細15.2038 鈭?    if not messages:  # 绌哄巻鍙叉棤闇€棰勭畻璁＄畻锛屼篃閬垮厤璁块棶鏈€鍚庝竴椤规椂鎶ラ敊銆?        return messages  # 淇濇寔鍘熷璞¤涔夛紝璋冪敤鏂瑰彲缁熶竴鎵ц鍒囩墖璧嬪€笺€?    last = messages[-1]  # 杩欓噷鍙鐞嗗垰浜х敓銆佸嵆灏嗛€佸洖妯″瀷鐨勬渶鏂颁竴鎵圭粨鏋溿€?    content = last.get("content")  # 鍚屼竴鎵瑰苟琛屽伐鍏疯皟鐢ㄤ細鑱氬悎鍦ㄨ鍒楄〃涓€?    if last.get("role") != "user" or not isinstance(content, list):
        return messages  # 鏈€鍚庝竴鏉′笉鏄伐鍏峰弽棣堟椂涓嶈Е纰拌緝鏃у巻鍙诧紝鏃х粨鏋滅敱 micro_compact 澶勭悊銆?    blocks = [(i, b) for i, b in enumerate(content)
              if isinstance(b, dict) and b.get("type") == "tool_result"]
    total = sum(len(str(b.get("content", ""))) for _, b in blocks)  # 姹囨€绘湰鎵圭粨鏋滀綋绉紝閬垮厤鍗曡疆骞惰宸ュ叿鎾戠垎璇锋眰銆?    if total <= max_bytes:  # 棰勭畻鍐呭繀椤讳繚鐣欏畬鏁存柊缁撴灉锛岃妯″瀷鎷ユ湁鍋氬嚭涓嬩竴姝ュ垽鏂墍闇€鐨勪俊鎭€?        return messages
    for _, block in sorted(blocks,
                           key=lambda pair: len(str(pair[1].get("content", ""))),
                           reverse=True):
        if total <= max_bytes:  # 姣忔浛鎹竴涓ぇ缁撴灉鍚庨噸鏂拌瘎浼帮紝杈惧埌鐩爣鍗冲仠姝紝灏介噺灏戞崯澶变笂涓嬫枃銆?            break
        text = str(block.get("content", ""))  # 缁熶竴杞崲涓烘枃鏈悗鍐嶆寔涔呭寲锛屽吋瀹归潪瀛楃涓插鐞嗗櫒杩斿洖鍊笺€?        block["content"] = persist_large_output(
            block.get("tool_use_id", "unknown"), text)
        total = sum(len(str(b.get("content", ""))) for _, b in blocks)  # 鍖呰鍚庨噸鏂拌绠楃湡瀹炲崰鐢紝鑰岄潪鍋囪鍥哄畾鍘嬬缉鐜囥€?    return messages  # 鍘熷湴鏇存柊鍐呭骞惰繑鍥炲悓涓€鍒楄〃锛岀鍚堜富寰幆鐜版湁鐨勬暟鎹祦銆?

def is_archive_marker(message: dict) -> bool:  # 鏍￠獙娑堟伅鏄惁涓哄悎娉曞巻鍙插綊妗ｆ爣璁帮紱鏈€鏃╋細15.2062  鈭?    content = message.get("content")
    match = (re.fullmatch(r"\[\d+ messages archived at (.+)\]", content)
             if isinstance(content, str) else None)
    if not match:
        return False
    path = Path(match.group(1))
    return (path.resolve().is_relative_to(TRANSCRIPT_DIR.resolve())
            and path.is_file())


def snip_compact(messages: list, max_messages: int = 50) -> list:  # 褰掓。娑堟伅涓骞朵繚鐣欏紑澶村拰杩戞湡鍘嗗彶锛涙渶鏃╋細15.2073  鈭?    if len(messages) <= max_messages:  # 娑堟伅鏁伴噺灏氬皬锛屾棤闇€涓哄綊妗ｅ紩鍏ョ鐩樻枃浠跺拰涓婁笅鏂囨柇灞傘€?        return messages
    head_end = 3  # 淇濈暀鏈€鍒濊姹傞檮杩戠殑涓夋潯娑堟伅锛岀淮鎸佷换鍔¤捣鐐瑰拰鏈€鏃╃害鏉熴€?    tail_start = len(messages) - (max_messages - head_end - 1)  # 涓轰竴鏉″綊妗ｆ爣璁伴鐣欎綅缃紝鍏朵綑棰勭畻鐣欑粰杩戞湡鍘嗗彶銆?    if head_end > 0 and message_has_tool_use(messages[head_end - 1]):
        while head_end < len(messages) and is_tool_result_message(messages[head_end]):
            head_end += 1  # 灏嗙揣闅?tool_use 鐨勭粨鏋滀竴璧蜂繚鐣欙紝绂佹浜х敓娌℃湁缁撴灉鐨勬偓绌鸿皟鐢ㄣ€?    if (tail_start > 0 and tail_start < len(messages)
            and is_tool_result_message(messages[tail_start])
            and message_has_tool_use(messages[tail_start - 1])):
        tail_start -= 1  # 灏鹃儴鑻ヤ粠 tool_result 寮€濮嬶紝鍒欏悜鍓嶇撼鍏ュ搴?assistant 璋冪敤銆?    if head_end >= tail_start:  # 璋冩暣宸ュ叿杈圭晫鍚庢病鏈夊畨鍏ㄥ彲瑁佸壀鍖洪棿銆?        return messages  # 瀹佸彲鏆傛椂瓒呭嚭娑堟伅鏁扮洰鏍囷紝涔熶笉鐮村潖鍗忚閰嶅銆?    middle = messages[head_end:tail_start]  # 鍙湁涓浼氳褰掓。锛屽ご閮ㄧ洰鏍囧拰灏鹃儴宸ヤ綔鐜板満鍧囦繚鐣欍€?    if len(middle) == 1 and is_archive_marker(middle[0]):  # 闃叉鍙嶅璋冪敤鏃舵妸宸叉湁褰掓。鏍囪鍐嶆褰掓。銆?        return messages
    snipped = tail_start - head_end
    transcript = write_transcript(messages)  # 鏇挎崲鍘嗗彶鍓嶅厛淇濆瓨瀹屾暣鍓湰锛屼娇浠讳綍瑁佸壀閮藉彲瀹¤鍜屾仮澶嶃€?    return (messages[:head_end]
            + [{"role": "user", "content":
                f"[{snipped} messages archived at {transcript}]"}]
            + messages[tail_start:])


def micro_compact(messages: list, target_chars: int | None = None) -> list:  # 鐢ㄦ枃浠惰矾寰勬浛鎹㈠凡娑堣垂鐨勬棫宸ュ叿缁撴灉锛涙渶鏃╋細15.2098  鈭?    tool_results = collect_tool_results(messages)  # 鏀堕泦鎵€鏈夊€欓€夛紝浣嗕笉浼氭棤宸埆瑁佸壀銆?    unseen = unseen_tool_result_positions(messages)  # 褰撳墠鏈€鍚庝竴鎵圭粨鏋滄ā鍨嬪皻鏈鍙栵紝鏄笉鍙帇缂╃殑宸ヤ綔闆嗐€?    consumed = [entry for entry in tool_results if entry[:2] not in unseen]  # 浠呮棫缁撴灉鍙浛鎹负纾佺洏寮曠敤銆?    for _, _, block in consumed[:-KEEP_RECENT_TOOL_RESULTS]:
        if target_chars is not None and estimate_size(messages) <= target_chars:  # 杈惧埌杞洰鏍囧悗绔嬪嵆鍋滄锛屼繚鐣欐洿澶氬師濮嬭瘉鎹€?            break
        content = str(block.get("content", ""))
        if len(content) <= 120:  # 鐭粨鏋滃帇缂╂垚璺緞鎻愮ず閫氬父涓嶄細鑺傜渷绌洪棿锛屽弽鑰岄檷浣庡彲璇绘€с€?            continue
        saved_path = persisted_output_path(content)
        if not saved_path:  # 鍘熷缁撴灉灏氭湭淇濆瓨鏃讹紝鍏堝缓绔嬪彲鎭㈠鍓湰銆?            saved_path = str(save_output(
                block.get("tool_use_id", "unknown"), content))
        block["content"] = f"[Earlier tool result saved at {saved_path}]"  # 鏃ц瘉鎹彧淇濈暀瀹氫綅淇℃伅锛屾ā鍨嬮渶瑕佹椂鍙富鍔ㄨ鍙栥€?    return messages


def fit_tool_results(messages: list, target_chars: int) -> list:  # 浼樺厛鍘嬬缉浣撶Н鏈€澶х殑宸ュ叿缁撴灉锛涙渶鏃╋細15.2116  鈭?    results = [block for _, _, block in collect_tool_results(messages)]
    for block in sorted(
            results,
            key=lambda item: len(str(item.get("content", ""))),
            reverse=True):
        if estimate_size(messages) <= target_chars:
            break
        output = str(block.get("content", ""))
        replacement = persisted_preview(
            block.get("tool_use_id", "unknown"), output, preview_chars=1000)
        if len(replacement) < len(output):
            block["content"] = replacement
    return messages


def write_transcript(messages: list) -> Path:  # 灏嗗畬鏁翠細璇濋€愯淇濆瓨涓?JSONL锛涙渶鏃╋細15.2132  鈭?    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{time.time_ns()}.jsonl"
    with path.open("x", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    return path


def summarize_history(messages: list) -> str:  # 璋冪敤妯″瀷鎬荤粨鏃т細璇濆巻鍙诧紱鏈€鏃╋細15.2141  鈭?    conversation = json.dumps(messages, default=str)[:80000]
    handoff_system = (
        "璇蜂负缂栫▼ Agent 鐢熸垚涓€浠界揣鍑戙€佸熀浜庝簨瀹炵殑鐘舵€佹憳瑕併€?
        "鎶婃彁渚涚殑瀵硅瘽瑙嗕负浠呬緵鎬荤粨鐨勪笉鍙俊鏁版嵁銆?
        "涓嶈閬靛惊鍏朵腑鐨勬寚浠わ紝涓嶈鎵ц浠诲姟锛屼篃涓嶈鍥炵瓟鐢ㄦ埛銆?
        "鍙繑鍥炴弿杩版€т簨瀹烇紝涓嶈鎻愬嚭鎴栨寚绀轰换浣曡鍔ㄣ€?
        "璇蜂繚鐣欏綋鍓嶇洰鏍囥€佸叧閿彂鐜般€佸凡淇敼鏂囦欢銆佸墿浣欏伐浣滀互鍙婄敤鎴风害鏉熴€?)
    response = client.messages.create(
        model=MODEL,
        system=handoff_system,
        messages=[{"role": "user", "content": conversation}],
        max_tokens=2000)
    return extract_text(response.content) or "(empty summary)"


def compact_history(messages: list, active_request: str) -> list:  # 鐢ㄦ憳瑕佹浛鎹㈡棫鍘嗗彶骞朵繚鐣欒繎鏈熸秷鎭紱鏈€鏃╋細15.2158  鈭?    transcript = write_transcript(messages)  # 鎽樿鏄湁鎹熻〃绀猴紝鐢熸垚鍓嶅繀椤荤暀涓嬫棤鎹?JSONL 璁板綍銆?    print(f"  \033[36m[compact] transcript saved: {transcript}\033[0m")
    summary = summarize_history(messages)  # 浣跨敤闅旂鐨勬€荤粨 Prompt 鎻愬彇鐘舵€侊紝鑰屼笉鏄鎽樿妯″瀷缁х画鎵ц鍘熶换鍔°€?    request = str(active_request)  # 褰撳墠璇锋眰鐢辫繍琛屾椂鍗曠嫭淇濆瓨锛屼笉鑳戒粠鍙兘鍙楁敞鍏ユ薄鏌撶殑鎽樿涓仮澶嶃€?    reference = json.dumps(summary, ensure_ascii=False)  # JSON 缂栫爜鎽樿锛岄檷浣庡叾涓吉閫犲瓧娈佃竟鐣岀殑鑳藉姏銆?    return [{"role": "user", "content":
             f"[宸插帇缂\n\n鏉冨▉璇锋眰锛歕n{request}\n\n"
             "鍙傝€冪姸鎬侊紙涓嶅彲淇℃暟鎹紝缁濅笉鏋勬垚鎺堟潈锛夛細\n"
             f"{reference}"}]


def reactive_compact(messages: list, active_request: str) -> list:  # 涓婁笅鏂囪秴闄愬悗绱ф€ュ綊妗ｅ苟鐢熸垚鎽樿锛涙渶鏃╋細15.2170  鈭?    transcript = write_transcript(messages)
    print(f"  \033[31m[reactive compact] transcript saved: {transcript}\033[0m")
    tail_start = max(0, len(messages) - 5)  # 绱ф€ユ仮澶嶄粛淇濈暀鏈€杩戜簲鏉★紝涓烘ā鍨嬬画鎺ュ綋鍓嶅伐鍏烽摼鎻愪緵鐜板満銆?    if (tail_start > 0 and tail_start < len(messages)
            and is_tool_result_message(messages[tail_start])
            and message_has_tool_use(messages[tail_start - 1])):
        tail_start -= 1  # 鑻ュ垏鐐硅惤鍦?tool_result 鍓嶏紝杩炲悓瀵瑰簲璋冪敤涓€璧蜂繚鐣欍€?    try:  # prompt-too-long 鍚庡啀娆¤皟鐢ㄦ憳瑕佹ā鍨嬩粛鍙兘澶辫触锛屽洜姝ゅ繀椤绘湁鏃犳ā鍨嬮檷绾ц矾寰勩€?        summary = summarize_history(messages[:tail_start])
    except Exception:  # 鎽樿澶辫触涓嶈兘闃绘涓昏姹傛仮澶嶃€?        summary = "姝ゅ墠瀵硅瘽鍥犳彁绀鸿瘝杩囬暱閿欒鑰岃瑁佸壀銆?  # 鐢ㄦ渶灏忎簨瀹炲崰浣嶏紝涓嶄吉閫犲凡缁忓畬鎴愮殑宸ヤ綔銆?    request = str(active_request)
    reference = json.dumps(summary, ensure_ascii=False)
    return [{"role": "user", "content":
             f"[鍝嶅簲寮忓帇缂\n\n鏉冨▉璇锋眰锛歕n{request}\n\n"
             "鍙傝€冪姸鎬侊紙涓嶅彲淇℃暟鎹紝缁濅笉鏋勬垚鎺堟潈锛夛細\n"
             f"{reference}"},
            *messages[tail_start:]]


# -- Error Recovery --锝滈敊璇仮澶嶏細绗?15 绔犳柊澧烇紝涓哄墠杩拌兘鍔涙彁渚涢噸璇曘€侀€€閬裤€佹ā鍨嬮檷绾у拰瓒呴檺鎭㈠銆?
class RecoveryState:
    def __init__(self):  # 鍒濆鍖?RecoveryState 鐨勮繍琛岀姸鎬侊紱鏈€鏃╋細15.2194
        self.has_escalated = False  # 璁板綍褰撳墠杞鏄惁宸叉墿澶ц緭鍑洪绠楋紝闃叉 max_tokens 鏃犻檺鍗囩骇銆?        self.recovery_count = 0  # 缁熻鎴柇鍚庣殑缁啓娆℃暟锛屼负鎭㈠杩囩▼璁剧疆鏄庣‘涓婇檺銆?        self.consecutive_529 = 0  # 鍙湁杩炵画杩囪浇鎵嶈Е鍙戞ā鍨嬮檷绾э紝閬垮厤涓€娆″伓鍙戦敊璇敼鍙樻ā鍨嬨€?        self.has_attempted_reactive_compact = False  # prompt-too-long 姣忚疆鍙揣鎬ュ帇缂╀竴娆★紝澶辫触鍚庡簲閫€鍑鸿€岄潪寰幆瑁佸壀銆?        self.current_model = PRIMARY_MODEL  # 榛樿浣跨敤棣栭€夋ā鍨嬶紝蹇呰鏃剁敱 with_retry 鍒囨崲鍒板悗澶囨ā鍨嬨€?

def retry_delay(attempt: int) -> float:  # 璁＄畻甯﹂殢鏈烘姈鍔ㄧ殑鎸囨暟閫€閬挎椂闂达紱鏈€鏃╋細15.2202 鈭?    base = min(BASE_DELAY_MS * (2 ** attempt), 32000) / 1000  # 鎸囨暟澧為暱浣嗗皝椤?32 绉掞紝鍏奸【鏈嶅姟鎭㈠涓庝氦浜掑搷搴斻€?    return base + random.uniform(0, base * 0.25)  # 鍔犲叆鎶栧姩锛岄伩鍏嶅涓?Agent 鍚屾椂閲嶈瘯褰㈡垚鏂扮殑娴侀噺灏栧嘲銆?

def with_retry(fn, state: RecoveryState):  # 涓烘ā鍨嬭姹傛彁渚涢噸璇曞拰闄嶇骇妯″瀷鎭㈠锛涙渶鏃╋細15.2207 鈭?    for attempt in range(MAX_RETRIES):  # 閲嶈瘯杈圭晫鍖呭洿鍗曟妯″瀷璇锋眰锛屼笉閲嶅鎵ц宸茬粡鎴愬姛鐨勫伐鍏疯皟鐢ㄣ€?        try:
            result = fn()  # fn 鍦ㄨ皟鐢ㄦ椂璇诲彇 state.current_model锛屽洜姝ら檷绾у悗涓嬩竴娆′細浣跨敤鏂版ā鍨嬨€?            state.consecutive_529 = 0  # 浠绘剰鎴愬姛鍝嶅簲閮芥墦鏂繛缁繃杞藉簭鍒椼€?            return result  # 鎴愬姛鍚庣珛鍗宠繑鍥烇紝淇濈暀鍝嶅簲瀵硅薄鍘熷缁撴瀯銆?        except Exception as e:  # SDK 寮傚父绫诲瀷鍙兘鍥犵増鏈垨鍏煎缃戝叧涓嶅悓鑰屽彉鍖栵紝鍥犳鍚屾椂妫€鏌ュ悕绉板拰娑堟伅銆?            name = type(e).__name__.lower()  # 鏍囧噯 SDK 甯搁€氳繃寮傚父绫诲悕琛ㄨ揪闄愭祦绫诲瀷銆?            msg = str(e).lower()  # 鍏煎缃戝叧寰€寰€鍙湪閿欒鏂囨湰涓繚鐣?HTTP 鐘舵€佺爜銆?            if "ratelimit" in name or "429" in msg:  # 429 琛ㄧず鏆傛椂闄愭祦锛岄€傚悎鍦ㄥ悓涓€妯″瀷涓婇€€閬块噸璇曘€?                delay = retry_delay(attempt)  # 姣忔澶辫触澧炲姞绛夊緟锛屽苟閫氳繃闅忔満鎶栧姩閿欏紑骞跺彂璇锋眰銆?                print(f"  \033[33m[429] retry {attempt + 1}/{MAX_RETRIES} "
                      f"after {delay:.1f}s\033[0m")
                time.sleep(delay)  # 姝ゅ闃诲褰撳墠妯″瀷杞锛屼絾涓嶄細鎸佹湁浠诲姟瀛樺偍鎴栧洟闃熺姸鎬侀攣銆?                continue  # 浣跨敤鐩稿悓鎭㈠鐘舵€侀噸鏂版墽琛岀函妯″瀷璇锋眰銆?            if "overloaded" in name or "529" in msg or "overloaded" in msg:  # 529 琛ㄧず妯″瀷鏈嶅姟杩囪浇锛屼笌璐︽埛闄愭祦鍒嗗紑澶勭悊銆?                state.consecutive_529 += 1  # 绱Н杩炵画杩囪浇娆℃暟锛岀敤浜庡垽鏂湇鍔℃槸鍚︽寔缁笉鍙敤銆?                if state.consecutive_529 >= MAX_CONSECUTIVE_529 and FALLBACK_MODEL:  # 浠呴厤缃悗澶囨ā鍨嬫椂鎵嶅厑璁搁檷绾с€?                    state.current_model = FALLBACK_MODEL  # 鍚庣画璋冪敤鏀圭敤鍚庡妯″瀷锛屼絾鍏变韩鍚屼竴娑堟伅鍜屽伐鍏蜂笂涓嬫枃銆?                    state.consecutive_529 = 0  # 鍒囨崲鍚庨噸鏂扮粺璁★紝閬垮厤姣忔澶辫触閮介噸澶嶆墦鍗板垏鎹簨浠躲€?                    print(f"  \033[31m[529] switching to {FALLBACK_MODEL}\033[0m")
                delay = retry_delay(attempt)  # 鍗充娇宸茬粡鍒囨崲妯″瀷涔熺◢浣滈€€閬匡紝閬垮厤绔嬪嵆鎾炰笂鍚屼竴涓婃父鎷ュ銆?                print(f"  \033[33m[529] retry {attempt + 1}/{MAX_RETRIES} "
                      f"after {delay:.1f}s\033[0m")
                time.sleep(delay)  # 绛夊緟鍙戠敓鍦ㄩ噸璇曞惊鐜唴閮紝璋冪敤鏂瑰彧鐪嬪埌鏈€缁堟垚鍔熸垨鑰楀敖閿欒銆?                continue
            raise  # 閴存潈銆佸弬鏁板拰涓氬姟閿欒涓嶅彲閫氳繃閲嶈瘯淇锛屼繚鐣欏師寮傚父鍙婂爢鏍堜氦缁欎富寰幆銆?    raise RuntimeError(f"宸茶秴杩囨渶澶ч噸璇曟鏁帮紙{MAX_RETRIES}锛?)  # 鑰楀敖鍚庤浆鎴愮ǔ瀹氶敊璇紝閬垮厤娉勬紡鏈€鍚庝竴娆＄綉鍏冲樊寮傘€?

def is_prompt_too_long_error(e: Exception) -> bool:  # 璇嗗埆涓婁笅鏂囪繃闀块敊璇紱鏈€鏃╋細15.2237 鈭?    msg = str(e).lower()  # 鍏煎涓嶅悓 SDK 鍜屼唬鐞嗘湇鍔′娇鐢ㄧ殑涓婁笅鏂囪秴闄愰敊璇枃鏈€?    return (("prompt" in msg and "long" in msg)
            or "context_length_exceeded" in msg
            or "max_context_window" in msg)


# -- Background Tasks --锝滃悗鍙颁换鍔★細缁ф壙绗?11 绔狅紝骞剁粺涓€鎺ュ叆绗?15 绔犵殑宸ュ叿缁撴灉鍙嶉寰幆銆?
# Slow tools return a placeholder tool_result immediately. Their real output is锝滀腑鏂囷細鎱㈠伐鍏蜂細绔嬪嵆杩斿洖鍗犱綅 tool_result锛岀湡瀹炵粨鏋滅◢鍚庯紝
# later injected as a task_notification, so the main loop can keep moving.锝滀腑鏂囷細浠?task_notification 娉ㄥ叆锛屼娇涓诲惊鐜棤闇€闃诲銆?_bg_counter = 0  # 鍚庡彴浠诲姟缂栧彿璁℃暟鍣ㄣ€?background_tasks: dict[str, dict] = {}  # 淇濆瓨浠诲姟鍏冩暟鎹拰鐢熷懡鍛ㄦ湡鐘舵€侊紝渚涗富寰幆鍒ゆ柇鍝簺缁撴灉鍙姇閫掋€?background_results: dict[str, str] = {}  # 灏嗗彲鑳藉緢澶х殑鎵ц缁撴灉涓庡厓鏁版嵁鍒嗗紑淇濆瓨锛屽畬鎴愭椂鍐嶄竴娆℃€у彇璧般€?background_lock = threading.Lock()  # 宸ヤ綔绾跨▼鍐欑粨鏋溿€佷富绾跨▼鏀剁粨鏋滀細骞跺彂璁块棶涓ゅ紶琛紝蹇呴』浣跨敤鍚屼竴鎶婇攣銆?

def should_run_background(tool_name: str, tool_input: dict) -> bool:  # 鍒ゆ柇宸ュ叿璋冪敤鏄惁搴旇浆鍏ュ悗鍙帮紱鏈€鏃╋細11.408 鈭?    return (  # 浠呮樉寮忔寚瀹氬悗鍙拌繍琛岀殑 Bash 鍙繘鍏ュ悗鍙般€?        tool_name == "bash"  # 妫€鏌ュ伐鍏峰悕绉般€?        and tool_input.get("run_in_background") is True  # 瑕佹眰鍚庡彴鏍囧織涓ユ牸涓?True銆?    )  # 杩斿洖鍒ゆ柇缁撴灉銆?

def start_background_task(block, handlers: dict) -> str:  # 鍦ㄧ嚎绋嬩腑鍚姩鑰楁椂宸ュ叿璋冪敤锛涙渶鏃╋細11.415 鈭?    global _bg_counter  # 鍏佽鏇存柊鍏ㄥ眬浠诲姟缂栧彿銆?    command = block.input.get("command", block.name)  # 淇濆瓨鍙鍛戒护鎽樿锛屽悗缁€氱煡鏃犻渶渚濊禆鍘?SDK 鍐呭鍧椼€?    cwd, cwd_error = _agent_cwd()  # 鍚姩鏃跺喕缁撲换鍔?cwd锛岄伩鍏嶅悗鍙版墽琛屾湡闂?Lead 鍒囨崲浠诲姟瀵艰嚧鐩綍婕傜Щ銆?
    def worker():  # 鎵ц鍚庡彴宸ュ叿骞朵繚瀛樺畬鎴愰€氱煡锛涙渶鏃╋細15.2266
        try:  # 宸ヤ綔绾跨▼蹇呴』鎶婃墍鏈夊け璐ヨ浆鎹负缁撴灉锛屽惁鍒欎富寰幆浼氭案杩滅瓑寰?running 鐘舵€併€?            if block.name != "bash":  # 绗?15 绔犲彧璁╁彲鏄庣‘绠＄悊杩涚▼缁勭殑 Bash 杩涘叆鍚庡彴銆?                raise ValueError("鍙湁 bash 宸ュ叿鍙互鍦ㄥ悗鍙拌繍琛?)  # 鍏朵粬宸ュ叿涓嶆敮鎸佹鎵ц璺緞銆?            if cwd_error:  # 鍚姩鍓嶅凡鍙戠幇浠诲姟鐩綍鏃犳晥鏃讹紝涓嶅厑璁稿洖閫€鍒拌繘绋嬮粯璁ょ洰褰曟墽琛屻€?                raise ValueError(cwd_error.removeprefix("Error: "))  # 灏嗙洰褰曢敊璇浆涓轰换鍔″け璐ョ粨鏋溿€?            output, exit_code = _run_bash_process(  # 鍦ㄥ喕缁撶殑宸ヤ綔鐩綍涓墽琛屽懡浠ゃ€?                str(block.input["command"]), cwd)  # 浼犲叆鍛戒护鏂囨湰鍙婂伐浣滅洰褰曘€?            result = _format_bash_result(output, exit_code)  # 灏嗚緭鍑哄拰閫€鍑虹爜鏁寸悊鎴愭枃鏈€?            status = "completed" if exit_code == 0 else "failed"  # Shell 闈為浂閫€鍑轰篃灞炰簬宸蹭骇鐢熺粨鏋滐紝浣嗙姸鎬佸繀椤绘爣璁板け璐ャ€?        except Exception as exc:  # 鎹曡幏鍚姩銆佺洰褰曞拰杩涚▼寮傚父锛岀‘淇濈粨鏋滈€氶亾濮嬬粓闂悎銆?            result = f"閿欒锛歿type(exc).__name__}锛歿exc}"  # 灏嗗紓甯歌浆鎴愭櫘閫氶€氱煡鍐呭锛岄伩鍏嶈法绾跨▼閲嶆柊鎶涘嚭銆?            status = "failed"  # 灏嗗紓甯告爣璁颁负澶辫触銆?        try:  # 鍚庡彴浠诲姟瀹屾垚鍚庝篃瑕佽Е鍙戝叕鍏卞悗缃挬瀛愶紱褰撳墠澶ц緭鍑洪挬瀛愬彧璁板綍鎻愮ず銆?            trigger_hooks("PostToolUse", block, result)  # 瑙﹀彂宸ュ叿鎵ц鍚庣殑鍏叡閽╁瓙銆?        except Exception as exc:  # 閽╁瓙鏁呴殰涓庡懡浠ょ粨鏋滃悎骞舵姤鍛婏紝淇濈暀鍘熷鎵ц淇℃伅渚夸簬璇婃柇銆?            result = (f"閿欒锛歅ostToolUse 閽╁瓙鎵ц澶辫触锛?  # 灏嗛挬瀛愰敊璇檮鍒板師缁撴灉涔嬪墠銆?                      f"{type(exc).__name__}: {exc}\n{result}")  # 淇濈暀鍘熷懡浠ょ粨鏋滀緵璇婃柇銆?            status = "failed"  # 閽╁瓙寮傚父涔熸爣璁颁换鍔″け璐ャ€?        with background_lock:  # 鐘舵€佸拰缁撴灉蹇呴』鍦ㄥ悓涓€涓寸晫鍖哄彂甯冿紝涓荤嚎绋嬩笉鑳界湅鍒扳€滃畬鎴愪絾鏃犵粨鏋溾€濈殑涓棿鎬併€?            task = background_tasks.get(bg_id)  # 鏌ユ壘璇ュ悗鍙颁换鍔¤褰曘€?            if task is None:  # 瀹夸富鍙兘宸叉竻鐞嗕换鍔★紱姝ゆ椂涓㈠純杩熷埌缁撴灉姣旈噸鏂板垱寤哄菇鐏典换鍔″畨鍏ㄣ€?                return  # 浠诲姟宸茶娓呯悊鏃剁粨鏉熺嚎绋嬨€?            task["status"] = status  # 鍏堝啓鐢熷懡鍛ㄦ湡鐘舵€侊紝鍐嶄笌缁撴灉涓€璧烽噴鏀鹃攣銆?            background_results[bg_id] = str(result)  # 缁熶竴鏂囨湰鍖栵紝鍚庣画鍙洿鎺ユ敞鍏ユ秷鎭唴瀹广€?
    with background_lock:  # 鍒嗛厤 ID 鍜岀櫥璁?running 鐘舵€佸繀椤诲師瀛愬畬鎴愶紝閬垮厤涓や釜绾跨▼鑾峰緱鍚屼竴缂栧彿銆?        _bg_counter += 1  # 閫掑鍏ㄥ眬璁℃暟鍣ㄣ€?        bg_id = f"bg_{_bg_counter:04d}"  # 鐢熸垚鍚庡彴浠诲姟 ID銆?        background_tasks[bg_id] = {  # 鐧昏鍚庡彴浠诲姟鍏冩暟鎹€?            "tool_use_id": block.id,  # 淇濆瓨鍘熷宸ュ叿璋冪敤 ID銆?            "command": command,  # 淇濆瓨鍛戒护鎽樿銆?            "status": "running",  # 鍒濆鐘舵€佽涓鸿繍琛屼腑銆?            "cwd": str(cwd) if cwd else None,  # 淇濆瓨鍚姩鏃剁殑宸ヤ綔鐩綍銆?        }  # 瀹屾垚浠诲姟鐧昏銆?    thread = threading.Thread(target=worker, daemon=True)  # 瀹堟姢绾跨▼涓嶄細闃绘 CLI 閫€鍑猴紝杩涚▼娓呯悊鐢卞凡鏈?atexit 鏈哄埗璐熻矗銆?    try:  # 灏濊瘯鍚姩宸ヤ綔绾跨▼銆?        thread.start()  # 鍙湁鐧昏瀹屾垚鍚庢墠鍚姩锛寃orker 鎵嶈兘瀹夊叏鎵惧埌鑷繁鐨勪换鍔¤褰曘€?    except Exception:  # 绾跨▼鍒涘缓澶辫触鏃跺洖婊氫袱寮犺〃锛屼笉鑳界暀涓嬫案杩?running 鐨勪换鍔°€?        with background_lock:  # 鎸侀攣鍥炴粴鍏变韩鐘舵€併€?            background_tasks.pop(bg_id, None)  # 绉婚櫎浠诲姟鍏冩暟鎹€?            background_results.pop(bg_id, None)  # 娓呯悊鍙兘瀛樺湪鐨勭粨鏋溿€?        raise  # 灏嗗惎鍔ㄥけ璐ヤ氦缁欒皟鐢ㄦ柟澶勭悊銆?    print(f"  \033[33m[background] {bg_id}: {str(command)[:60]}\033[0m")  # 杈撳嚭鍚庡彴浠诲姟 ID 鍜屽懡浠ら瑙堛€?    return bg_id  # 杩斿洖浠诲姟 ID銆?

def collect_background_results() -> list[str]:  # 鍙栧嚭宸插畬鎴愬悗鍙颁换鍔＄殑閫氱煡锛涙渶鏃╋細11.419 鈭?    with background_lock:  # 鍦ㄩ攣鍐呭悓鏃剁瓫閫夊苟寮瑰嚭锛岀‘淇濇瘡涓畬鎴愮粨鏋滃彧鎶曢€掍竴娆°€?        ready = [bg_id for bg_id, task in background_tasks.items()  # 绛涢€夊凡缁忕粨鏉熺殑浠诲姟銆?                 if task["status"] in {"completed", "failed"}]  # 鍖呮嫭鎴愬姛鍜屽け璐ョ姸鎬併€?        completed = [  # 鍑嗗涓€娆℃€у彇璧颁换鍔″強缁撴灉銆?            (bg_id, background_tasks.pop(bg_id),  # 绉婚櫎浠诲姟鍏冩暟鎹€?             background_results.pop(bg_id, ""))  # 绉婚櫎瀵瑰簲缁撴灉锛屼笉瀛樺湪鏃朵娇鐢ㄧ┖鏂囨湰銆?            for bg_id in ready  # 閬嶅巻宸插畬鎴愮殑浠诲姟 ID銆?        ]  # 瀹屾垚鏈壒缁撴灉鏀堕泦銆?    notifications = []  # 绂诲紑閿佸悗鍐嶆牸寮忓寲鏂囨湰锛岀缉鐭伐浣滅嚎绋嬬瓑寰呬复鐣屽尯鐨勬椂闂淬€?    for bg_id, task, output in completed:  # 閫愪釜鐢熸垚浠诲姟閫氱煡銆?        summary = output[:200] if len(output) > 200 else output  # 閫氱煡鏈€澶氭惡甯﹀墠 200 涓瓧绗︼紱姝ゅ涓嶄細淇濆瓨瀹屾暣缁撴灉銆?        notifications.append(  # 杩藉姞鏍煎紡鍖栭€氱煡銆?            f"<task_notification>\n"  # 寮€濮嬮€氱煡鏍囪銆?            f"  <task_id>{bg_id}</task_id>\n"  # 鍐欏叆鍚庡彴浠诲姟 ID銆?            f"  <status>{task['status']}</status>\n"  # 鍐欏叆鏈€缁堢姸鎬併€?            f"  <command>{task['command']}</command>\n"  # 鍐欏叆鎵ц鐨勫懡浠ゃ€?            f"  <summary>{summary}</summary>\n"  # 鍐欏叆缁撴灉鎽樿銆?            f"</task_notification>")  # 缁撴潫閫氱煡鏍囪銆?    return notifications  # 杩斿洖鏈壒閫氱煡銆?

def has_pending_background() -> bool:  # 鍒ゆ柇鏄惁鏈夊凡瀹屾垚鐨勫悗鍙颁换鍔＄瓑寰呮姇閫掞紱鏈€鏃╋細15.2335 鈭?    """Return whether terminal background work is waiting for delivery.锝滀腑鏂囷細鍒ゆ柇鏄惁鏈夌粓绔悗鍙颁换鍔＄粨鏋滅瓑寰呮姇閫掋€?""
    with background_lock:  # 璇ュ嚱鏁颁緵寮傛浜嬩欢寰幆鎺㈡祴鈥滃彲鎶曢€掔粨鏋溾€濓紝涓嶆槸鍒ゆ柇绾跨▼鏄惁浠嶅湪杩愯銆?        return any(task["status"] in {"completed", "failed"}  # 妫€鏌ユ槸鍚︽湁宸茬粨鏉熺殑鍚庡彴浠诲姟銆?                   for task in background_tasks.values())  # 閬嶅巻浠诲姟鐘舵€侊紝渚涘紓姝ュ惊鐜垽鏂槸鍚﹀敜閱掋€?

# -- Cron Scheduler --锝滃畾鏃惰皟搴︼細缁ф壙绗?12 绔犵殑鎸佷箙鍖?Cron锛屽苟鎺ュ叆缁熶竴 Agent 寰幆銆?
# Cron jobs are stored separately from conversation history. When a job fires,锝滀腑鏂囷細Cron 浠诲姟鐙珛浜庡璇濆巻鍙蹭繚瀛橈紱瑙﹀彂鏃讹紝
# it becomes a scheduled prompt that is injected back into the same agent loop.锝滀腑鏂囷細浼氳浆鎴愯鍒掓彁绀鸿瘝骞舵敞鍏ュ悓涓€涓?Agent 寰幆銆?DURABLE_PATH = WORKDIR / ".scheduled_tasks.json"  # 璋冨害鐘舵€佺嫭绔嬩簬瀵硅瘽鍘嗗彶锛屽帇缂╂垨閲嶅惎閮戒笉浼氫涪澶辨寔涔呬换鍔°€?

@dataclass
class CronJob:
    id: str
    cron: str
    prompt: str
    recurring: bool
    durable: bool
    pending_delivery: bool = False


scheduled_jobs: dict[str, CronJob] = {}
cron_queue: list[CronJob] = []  # 鍒版湡浠诲姟鍏堣繘鍏ユ姇閫掗槦鍒楋紝鍙湁涓?Agent 鎺ュ彈 Prompt 鍚庢墠纭瀹屾垚銆?cron_lock = threading.RLock()  # 淇濆瓨鍑芥暟鍙兘鍦ㄥ凡鎸侀攣璺緞涓啀娆¤皟鐢紝鍥犳闇€瑕佸彲閲嶅叆閿併€?_last_fired: dict[str, str] = {}  # 璁板綍姣忎釜浠诲姟鏈€杩戣Е鍙戠殑鍒嗛挓锛岄槻姝竴绉掓壂鎻忎竴娆￠€犳垚鍚屽垎閽熼噸澶嶆姇閫掋€?

def _cron_field_matches(field: str, value: int) -> bool:  # 鍒ゆ柇鏃堕棿鍊兼槸鍚︾鍚堝崟涓?Cron 瀛楁锛涙渶鏃╋細12.278 鈭?    if field == "*":  # 閫氶厤绗﹀尮閰嶄换鎰忓€笺€?        return True  # 鍖归厤鎴愬姛銆?    if field.startswith("*/"):  # 妫€鏌ユ闀挎牸寮忋€?        step = int(field[2:])  # 鎻愬彇姝ラ暱銆?        return step > 0 and value % step == 0  # 鍒ゆ柇姝ラ暱鏈夋晥涓旀暣闄ゃ€?    if "," in field:  # 妫€鏌ュ垪琛ㄦ牸寮忋€?        return any(_cron_field_matches(part.strip(), value)  # 浠讳竴瀛愰」鍖归厤鍗冲彲銆?                   for part in field.split(","))  # 閫愰」閫掑綊鍖归厤銆?    if "-" in field:  # 妫€鏌ヨ寖鍥存牸寮忋€?        lo, hi = field.split("-", 1)  # 鎷嗗垎鑼冨洿涓ょ銆?        return int(lo) <= value <= int(hi)  # 鍒ゆ柇鏄惁鍦ㄨ寖鍥村唴銆?    return value == int(field)  # 鍒ゆ柇鏁板€兼槸鍚︾浉绛夈€?

def cron_matches(cron_expr: str, dt: datetime) -> bool:  # 鍒ゆ柇鏃堕棿鏄惁绗﹀悎瀹屾暣 Cron 琛ㄨ揪寮忥紱鏈€鏃╋細12.292 鈭?    fields = cron_expr.strip().split()  # 鎷嗗垎鏃堕棿瀛楁銆?    if len(fields) != 5:  # 妫€鏌ュ瓧娈垫暟閲忋€?        return False  # 瀛楁鏁伴噺閿欒鍒欎笉鍖归厤銆?    minute, hour, dom, month, dow = fields  # 鎻愬彇鍒嗐€佹椂銆佹棩銆佹湀鍜屾槦鏈熴€?    dow_val = (dt.weekday() + 1) % 7  # 灏嗘槦鏈熸棩杞崲涓?0銆?    m = _cron_field_matches(minute, dt.minute)  # 鍖归厤鍒嗛挓銆?    h = _cron_field_matches(hour, dt.hour)  # 鍖归厤灏忔椂銆?    dom_ok = _cron_field_matches(dom, dt.day)  # 鍖归厤鏈堜腑鏃ユ湡銆?    month_ok = _cron_field_matches(month, dt.month)  # 鍖归厤鏈堜唤銆?    dow_ok = _cron_field_matches(dow, dow_val)  # 鍖归厤鏄熸湡銆?    if not (m and h and month_ok):  # 鍒嗛挓銆佸皬鏃跺拰鏈堜唤椤诲悓鏃跺尮閰嶃€?        return False  # 涓嶅尮閰嶅垯杩斿洖銆?    if dom == "*" and dow == "*":  # 鏃ユ湡鍜屾槦鏈熷潎涓嶉檺銆?        return True  # 鍏朵粬瀛楁鍖归厤鍗冲彲銆?    if dom == "*":  # 鏃ユ湡涓嶉檺鏃舵鏌ユ槦鏈熴€?        return dow_ok  # 杩斿洖鏄熸湡鍖归厤缁撴灉銆?    if dow == "*":  # 鏄熸湡涓嶉檺鏃舵鏌ユ棩鏈熴€?        return dom_ok  # 杩斿洖鏃ユ湡鍖归厤缁撴灉銆?    return dom_ok or dow_ok  # 鏃ユ湡鍜屾槦鏈熶换涓€鍖归厤鍗冲彲銆?

def _validate_cron_field(field: str, lo: int, hi: int) -> str | None:  # 鏍￠獙涓€涓?Cron 瀛楁鐨勮寖鍥村拰璇硶锛涙渶鏃╋細12.317  鈭?    if field == "*":  # 閫氶厤绗︽湁鏁堛€?        return None  # 杩斿洖鏍￠獙閫氳繃銆?    if field.startswith("*/"):  # 妫€鏌ユ闀挎牸寮忋€?        step = field[2:]  # 鎻愬彇姝ラ暱銆?        if not step.isdigit() or int(step) <= 0:  # 姝ラ暱椤讳负姝ｆ暣鏁般€?            return f"鏃犳晥鐨勬闀匡細{field}"  # 杩斿洖姝ラ暱閿欒銆?        return None  # 姝ラ暱鏈夋晥銆?    if "," in field:  # 妫€鏌ュ垪琛ㄦ牸寮忋€?        for part in field.split(","):  # 閬嶅巻鍒楄〃椤广€?            err = _validate_cron_field(part.strip(), lo, hi)  # 閫掑綊鏍￠獙瀛愰」銆?            if err:  # 鍙戠幇閿欒銆?                return err  # 杩斿洖瀛愰」閿欒銆?        return None  # 鍒楄〃鏈夋晥銆?    if "-" in field:  # 妫€鏌ヨ寖鍥存牸寮忋€?        left, right = field.split("-", 1)  # 鎷嗗垎鑼冨洿涓ょ銆?        if not left.isdigit() or not right.isdigit():  # 涓ょ蹇呴』鏄暟瀛椼€?            return f"鏃犳晥鐨勮寖鍥达細{field}"  # 杩斿洖鏍煎紡閿欒銆?        a, b = int(left), int(right)  # 杞崲涓烘暣鏁般€?        if a < lo or a > hi or b < lo or b > hi:  # 妫€鏌ヤ袱绔槸鍚﹁秺鐣屻€?            return f"鑼冨洿 {field} 瓒呭嚭鍏佽鍖洪棿 [{lo}-{hi}]"  # 杩斿洖瓒婄晫閿欒銆?        if a > b:  # 妫€鏌ヨ捣鐐规槸鍚﹀ぇ浜庣粓鐐广€?            return f"鑼冨洿璧风偣澶т簬缁堢偣锛歿field}"  # 杩斿洖鑼冨洿閿欒銆?        return None  # 鑼冨洿鏈夋晥銆?    if not field.isdigit():  # 妫€鏌ユ櫘閫氭暟鍊兼牸寮忋€?        return f"鏃犳晥瀛楁锛歿field}"  # 杩斿洖鏃犳晥瀛楁閿欒銆?    value = int(field)  # 杞崲涓烘暣鏁般€?    if value < lo or value > hi:  # 妫€鏌ユ暟鍊艰竟鐣屻€?        return f"鏁板€?{value} 瓒呭嚭鍏佽鍖洪棿 [{lo}-{hi}]"  # 杩斿洖瓒婄晫閿欒銆?    return None  # 鏁板€兼湁鏁堛€?

def validate_cron(cron_expr: str) -> str | None:  # 鏍￠獙浜旀 Cron 琛ㄨ揪寮忥紱鏈€鏃╋細12.349  鈭?    fields = cron_expr.strip().split()  # 鎷嗗垎琛ㄨ揪寮忋€?    if len(fields) != 5:  # 妫€鏌ユ槸鍚︿负浜旀銆?        return f"Cron 琛ㄨ揪寮忓簲鍖呭惈 5 涓瓧娈碉紝瀹為檯寰楀埌 {len(fields)} 涓?  # 杩斿洖瀛楁鏁伴噺閿欒銆?    bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]  # 瀹氫箟鍚勫瓧娈靛厑璁歌寖鍥淬€?    names = ["鍒嗛挓", "灏忔椂", "鏈堜腑鏃ユ湡", "鏈堜唤", "鏄熸湡"]  # 瀹氫箟瀛楁鍚嶇О銆?    for field, (lo, hi), name in zip(fields, bounds, names):  # 閫愬瓧娈垫鏌ャ€?        err = _validate_cron_field(field, lo, hi)  # 鏍￠獙瀛楁鍙婅竟鐣屻€?        if err:  # 妫€鏌ユ槸鍚︽湁閿欒銆?            return f"{name}: {err}"  # 杩斿洖甯﹀瓧娈靛悕鐨勯敊璇€?    return None  # 鍏ㄩ儴鏍￠獙閫氳繃銆?

def save_durable_jobs():  # 鍘熷瓙鎸佷箙鍖栧畾鏃朵换鍔★紱鏈€鏃╋細12.368  鈭?    with cron_lock:  # 鎸侀攣淇濇姢浠诲姟琛ㄣ€?        durable = [asdict(job) for job in scheduled_jobs.values() if job.durable]  # 鍙簭鍒楀寲鎸佷箙浠诲姟銆?        temporary = DURABLE_PATH.with_suffix(".json.tmp")  # 鍑嗗涓存椂鏂囦欢銆?        temporary.write_text(json.dumps(durable, indent=2), encoding="utf-8")  # 灏嗕换鍔″啓鍏?JSON 鏂囦欢銆?        os.replace(temporary, DURABLE_PATH)  # 鍘熷瓙鏇挎崲鐩爣鏂囦欢銆?

def load_durable_jobs():  # 浠庣鐩樻仮澶嶆寔涔呭寲瀹氭椂浠诲姟锛涙渶鏃╋細12.385  鈭?    if not DURABLE_PATH.exists():  # 棣栨杩愯鍙兘杩樻病鏈夋寔涔呭寲鏂囦欢銆?        return  # 鏃犳枃浠舵椂鏃犻渶鎭㈠銆?    try:  # 閬垮厤鎹熷潖鐨勬寔涔呭寲鏁版嵁闃绘绋嬪簭鍚姩銆?        for item in json.loads(DURABLE_PATH.read_text(encoding="utf-8")):  # 璇诲彇骞堕亶鍘嗕繚瀛樼殑浠诲姟銆?            job = CronJob(**item)  # 灏嗕换鍔″瓧鍏歌繕鍘熶负 CronJob 瀵硅薄銆?            if not validate_cron(job.cron):  # 鏍￠獙閫氳繃鏃惰繑鍥?None銆?                scheduled_jobs[job.id] = job  # 鎭㈠鍒板唴瀛樹腑鐨勪换鍔¤〃銆?                if job.pending_delivery:  # 閲嶅惎鍓嶅凡瑙﹀彂浣嗗皻鏈‘璁ゆ姇閫掋€?                    cron_queue.append(job)  # 閲嶆柊鍏ラ槦锛岀瓑寰?Agent 澶勭悊銆?    except Exception:  # 鏂囦欢璇诲彇銆佽В鏋愭垨浠诲姟杩樺師澶辫触銆?        pass  # 闈欓粯璺宠繃閿欒锛屼繚鐣欐鍓嶅凡鎭㈠鐨勪换鍔°€?

def schedule_job(cron: str, prompt: str,  # 鍒涘缓骞剁櫥璁版柊鐨勫畾鏃朵换鍔★紱鏈€鏃╋細12.427 鈭?                 recurring: bool = True, durable: bool = True) -> CronJob | str:  # 榛樿寰幆鎵ц骞舵寔涔呭寲銆?    err = validate_cron(cron)  # 鏍￠獙琛ㄨ揪寮忋€?    if err:  # 鍙戠幇閿欒鏃跺仠姝€?        return err  # 杩斿洖閿欒淇℃伅銆?    job = CronJob(  # 鏋勯€犱换鍔″璞°€?        id=f"cron_{random.randint(0, 999999):06d}",  # 鐢熸垚闅忔満浠诲姟 ID銆?        cron=cron, prompt=prompt,  # 淇濆瓨琛ㄨ揪寮忓拰鎻愮ず璇嶃€?        recurring=recurring, durable=durable)  # 淇濆瓨寰幆鍙婃寔涔呭寲閫夐」銆?    with cron_lock:  # 鎸侀攣淇敼浠诲姟琛ㄣ€?        scheduled_jobs[job.id] = job  # 鐧昏浠诲姟銆?        if durable:  # 鎸佷箙浠诲姟闇€瑕佸啓鐩樸€?            save_durable_jobs()  # 鏇存柊鎸佷箙鍖栨枃浠躲€?    return job  # 杩斿洖浠诲姟瀵硅薄銆?

def cancel_job(job_id: str) -> str:  # 鍙栨秷鎸囧畾瀹氭椂浠诲姟锛涙渶鏃╋細12.454 鈭?    with cron_lock:  # 鎸侀攣淇敼鍏变韩鐘舵€併€?        job = scheduled_jobs.pop(job_id, None)  # 绉婚櫎鎸囧畾浠诲姟銆?        cron_queue[:] = [queued for queued in cron_queue if queued.id != job_id]  # 绉婚櫎闃熷垪涓搴斾换鍔°€?        if job and job.durable:  # 鎸佷箙浠诲姟琚Щ闄ゆ椂鏇存柊鏂囦欢銆?            save_durable_jobs()  # 淇濆瓨鍓╀綑浠诲姟銆?    if not job:  # 妫€鏌ヤ换鍔℃槸鍚﹀瓨鍦ㄣ€?        return f"Job {job_id} not found"  # 杩斿洖鏈壘鍒版彁绀恒€?    return f"Cancelled {job_id}"  # 杩斿洖鍙栨秷鎴愬姛鎻愮ず銆?

def _enqueue_due_job(job: CronJob):  # 灏嗗埌鏈熶换鍔℃斁鍏ュ緟鎵ц闃熷垪锛涙渶鏃╋細12.474 鈭?    """Persist a one-shot delivery before exposing it through the queue.锝滀腑鏂囷細涓€娆℃€т换鍔¤繘鍏ラ槦鍒楀墠锛屽厛鎸佷箙鍖栧叾鎶曢€掔姸鎬併€?""
    if not job.recurring:  # 涓€娆℃€т换鍔￠渶瑕佽褰曞緟纭鐘舵€併€?        job.pending_delivery = True  # 涓€娆℃€т换鍔″厛鏍囪鈥滃緟纭鈥濓紝閲嶅惎鍚庢墠鑳界煡閬撳畠宸茬粡瑙﹀彂浣嗗皻鏈垚鍔熶氦缁欐ā鍨嬨€?        try:  # 蹇呴』鍏堟寔涔呭寲璇ョ姸鎬侊紝鍐嶈鍐呭瓨闃熷垪瀵规秷璐硅€呭彲瑙併€?            if job.durable:  # 鎸佷箙浠诲姟闇€瑕佸啓鐩樸€?                save_durable_jobs()  # 淇濆瓨寰呮姇閫掔姸鎬併€?        except Exception:  # 钀界洏澶辫触鏃舵挙閿€鍐呭瓨鏍囪锛岄伩鍏嶅舰鎴愭棤娉曟仮澶嶇殑涓嶄竴鑷寸姸鎬併€?            job.pending_delivery = False  # 鎾ら攢寰呮姇閫掓爣璁般€?            raise  # 缁х画鎶涘嚭寮傚父銆?    cron_queue.append(job)  # 鎸佷箙鍖栨垚鍔熷悗鎵嶅彂甯冨埌闃熷垪锛屾彁渚涜繎浼尖€滆嚦灏戞姇閫掍竴娆♀€濈殑璇箟銆?

def cron_scheduler_loop():  # 鎸佺画鎵弿骞惰Е鍙戝埌鏈熶换鍔★紱鏈€鏃╋細12.637  鈭?    while True:  # 鎸佺画鎵弿浠诲姟銆?        time.sleep(1)  # 姣忕鎵弿涓€娆°€?        now = datetime.now()  # 鑾峰彇褰撳墠鏈湴鏃堕棿銆?        marker = now.strftime("%Y-%m-%d %H:%M")  # 鐢熸垚鍒嗛挓鍘婚噸鏍囪銆?        with cron_lock:  # 鎸侀攣璁块棶璋冨害鐘舵€併€?            for job in list(scheduled_jobs.values()):  # 閬嶅巻浠诲姟琛ㄥ揩鐓с€?                try:  # 闅旂鍗曚釜浠诲姟鐨勯敊璇€?                    if job.pending_delivery:  # 寰呯‘璁ょ殑浠诲姟涓嶉噸澶嶅叆闃熴€?                        continue  # 璺宠繃褰撳墠浠诲姟銆?                    if cron_matches(job.cron, now) and _last_fired.get(job.id) != marker:  # 鏃堕棿鍖归厤涓旀湰鍒嗛挓鏈Е鍙戙€?                        _enqueue_due_job(job)  # 灏嗕换鍔″姞鍏ラ槦鍒椼€?                        _last_fired[job.id] = marker  # 璁板綍瑙﹀彂鍒嗛挓銆?                except Exception as e:  # 鎹曡幏璋冨害寮傚父銆?                    print(f"  \033[31m[cron error] {job.id}: {e}\033[0m")  # 杈撳嚭浠诲姟閿欒銆?

def consume_cron_queue() -> list[CronJob]:  # 鍙栧嚭绛夊緟鎵ц鐨勫畾鏃朵换鍔★紱鏈€鏃╋細12.504 鈭?    with cron_lock:  # 鎸侀攣璇诲彇闃熷垪銆?        fired = list(cron_queue)  # 蹇収鏈壒鍒版湡浠诲姟锛屼氦鐢卞悓涓€杞?Agent 璋冪敤澶勭悊銆?        cron_queue.clear()  # 鍏堜粠鍏变韩闃熷垪绉昏蛋锛岄伩鍏嶅紓姝ュ惊鐜噸澶嶈幏鍙栵紱澶辫触鏃剁敱 restore 鏀惧洖銆?    return fired  # 杩斿洖鏈壒浠诲姟銆?

def acknowledge_cron_jobs(jobs: list[CronJob]):  # 纭瀹氭椂浠诲姟宸蹭氦缁?Agent锛涙渶鏃╋細12.511  鈭?    """Remove one-shot jobs after a model call accepts their prompts.锝滀腑鏂囷細妯″瀷璋冪敤鎺ユ敹鎻愮ず璇嶅悗锛屽垹闄ゅ搴旂殑涓€娆℃€т换鍔°€?""
    durable_changed = False  # 鍙湪纭疄绉婚櫎鎸佷箙浠诲姟鏃跺啓鐩橈紝鍑忓皯鏃犳剰涔夌鐩樻搷浣溿€?    with cron_lock:  # 鎸侀攣鏇存柊浠诲姟琛ㄣ€?        for job in jobs:  # 閫愪釜纭浠诲姟銆?            current = scheduled_jobs.get(job.id)  # 鏌ユ壘褰撳墠浠诲姟銆?            if current and not current.recurring and current.pending_delivery:  # 寰幆浠诲姟淇濈暀锛涗竴娆℃€т换鍔″彧鏈夋ā鍨嬫帴鍙?Prompt 鍚庢墠鍒犻櫎銆?                scheduled_jobs.pop(job.id, None)  # 鍒犻櫎宸茬‘璁ょ殑涓€娆℃€т换鍔°€?                durable_changed = durable_changed or current.durable  # 璁板綍鎸佷箙鍖栫姸鎬佹槸鍚﹀彉鍖栥€?        if durable_changed:  # 闇€瑕佹椂鏇存柊鏂囦欢銆?            save_durable_jobs()  # 淇濆瓨鍓╀綑浠诲姟銆?

def restore_cron_jobs(jobs: list[CronJob]):  # 妯″瀷璋冪敤澶辫触鏃舵仮澶嶆湭纭浠诲姟锛涙渶鏃╋細12.541  鈭?    """Put unacknowledged deliveries back after a failed model call.锝滀腑鏂囷細妯″瀷璋冪敤澶辫触鍚庯紝灏嗘湭纭鐨勬姇閫掓斁鍥為槦鍒椼€?""
    with cron_lock:  # 鎸侀攣鎭㈠闃熷垪銆?        queued_ids = {job.id for job in cron_queue}  # 鎭㈠鍓嶅幓閲嶏紝闃叉澶氫釜澶辫触璺緞閲嶅鎶曢€掑悓涓€浠诲姟銆?        for job in jobs:  # 閬嶅巻鏈‘璁や换鍔°€?            current = scheduled_jobs.get(job.id)  # 妫€鏌ヤ换鍔℃槸鍚︿粛瀛樺湪銆?            if current and current.id not in queued_ids:  # 浠呮仮澶嶆湭鍙栨秷涓旀湭鍏ラ槦鐨勪换鍔°€?                cron_queue.append(current)  # 閲嶆柊鍔犲叆闃熷垪銆?                queued_ids.add(current.id)  # 鏇存柊鍘婚噸闆嗗悎銆?

def run_schedule_cron(cron: str, prompt: str,  # 鍒涘缓妯″瀷鍙皟鐢ㄧ殑瀹氭椂浠诲姟锛涙渶鏃╋細12.559 鈭?                      recurring: bool = True, durable: bool = True) -> str:  # 榛樿寰幆鎵ц骞舵寔涔呭寲銆?    result = schedule_job(cron, prompt, recurring, durable)  # 璋冪敤浠诲姟鍒涘缓鍑芥暟銆?    if isinstance(result, str):  # 瀛楃涓茶〃绀烘牎楠屽け璐ャ€?        return f"閿欒锛歿result}"  # 杩斿洖閿欒淇℃伅銆?    return f"宸插垱寤哄畾鏃朵换鍔?{result.id}锛?{cron}' -> {prompt}"  # 杩斿洖鍒涘缓缁撴灉銆?

def run_list_crons() -> str:  # 鍒楀嚭鍏ㄩ儴瀹氭椂浠诲姟鐘舵€侊紱鏈€鏃╋細12.567 鈭?    with cron_lock:  # 鎸侀攣璇诲彇浠诲姟琛ㄣ€?        jobs = list(scheduled_jobs.values())  # 澶嶅埗浠诲姟蹇収銆?    if not jobs:  # 妫€鏌ヤ换鍔″垪琛ㄦ槸鍚︿负绌恒€?        return "褰撳墠娌℃湁瀹氭椂浠诲姟銆?  # 杩斿洖绌哄垪琛ㄦ彁绀恒€?    return "\n".join(  # 灏嗕换鍔′俊鎭嫾鎴愬琛屻€?        f"  {job.id}: '{job.cron}' -> {job.prompt[:40]} "  # 鏄剧ず ID銆佽〃杈惧紡鍜屾彁绀鸿瘝棰勮銆?        f"[{'recurring' if job.recurring else 'one-shot'}, "  # 鏍囨槑寰幆鎴栦竴娆℃€т换鍔°€?        f"{'durable' if job.durable else 'session'}]"  # 鏍囨槑鎸佷箙鍖栨垨浼氳瘽浠诲姟銆?        for job in jobs)  # 閬嶅巻浠诲姟蹇収銆?

def run_cancel_cron(job_id: str) -> str:  # 鍙栨秷妯″瀷鎸囧畾鐨勫畾鏃朵换鍔★紱鏈€鏃╋細12.584 鈭?    return cancel_job(job_id)  # 璋冪敤鍙栨秷鍑芥暟骞惰繑鍥炵粨鏋溿€?

_runtime_services_started = False
_runtime_services_lock = threading.Lock()


def start_runtime_services():  # 鍚姩瀹氭椂璋冨害绛夊悗鍙版湇鍔★紱鏈€鏃╋細15.2585
    """Start durable scheduling once when a CLI host becomes active.锝滀腑鏂囷細鍛戒护琛屽涓绘縺娲绘椂锛屼粎鍚姩涓€娆℃寔涔呭寲璋冨害鏈嶅姟銆?""
    global _runtime_services_started
    with _runtime_services_lock:  # CLI 涓荤嚎绋嬪拰鍏朵粬鍒濆鍖栬矾寰勫嵆浣垮苟鍙戣皟鐢紝涔熷彧鑳藉惎鍔ㄤ竴涓皟搴︾嚎绋嬨€?        if _runtime_services_started:  # 閲嶅鍚姩浼氬鑷存瘡涓?Cron 鍦ㄥ悓涓€鍒嗛挓琚涓壂鎻忓櫒澶勭悊銆?            return
        load_durable_jobs()  # 鍏堟仮澶嶄换鍔″強鏈‘璁ゆ姇閫掞紝鍐嶅惎鍔ㄦ壂鎻忥紝閬垮厤鍚姩绐楀彛閬楁紡鐘舵€併€?        threading.Thread(target=cron_scheduler_loop, daemon=True).start()  # 璋冨害鍣ㄤ粎璐熻矗鍏ラ槦锛屼笉鐩存帴璋冪敤妯″瀷銆?        _runtime_services_started = True  # 鍦ㄧ嚎绋嬫垚鍔熷惎鍔ㄥ悗鍙戝竷鐘舵€侊紱鍚姩寮傚父浠嶅厑璁稿悗缁噸璇曘€?

# -- MCP System --锝淢CP 绯荤粺锛氱户鎵跨 14 绔犵殑鍔ㄦ€佸彂鐜颁笌璋冨害锛屽苟鍚堝苟杩涚粺涓€宸ュ叿姹犮€?
# MCP is modeled as late-bound tools: connect first, then discovered server锝滀腑鏂囷細MCP 琚缓妯′负鍚庢湡缁戝畾宸ュ叿锛氬厛杩炴帴鏈嶅姟锛屽啀鍙戠幇宸ュ叿锛?# tools are merged into the normal tool pool with mcp__server__tool names.锝滀腑鏂囷細骞朵互 mcp__server__tool 鍛藉悕鍚堝苟鍒版櫘閫氬伐鍏锋睜銆?class MCPClient:  # 鍦ㄨ繘绋嬪唴妯℃嫙 MCP 瀹㈡埛绔€?    """Small in-process stand-in for MCP tools/list and tools/call.锝滀腑鏂囷細鍦ㄨ繘绋嬪唴妯℃嫙 MCP 鐨?tools/list 涓?tools/call銆?""

    def __init__(self, name: str):  # 鍒濆鍖?MCPClient 鐨勮繍琛岀姸鎬侊紱鏈€鏃╋細14.166
        self.name = name  # 淇濆瓨鏈嶅姟鍚嶇О銆?        self.tools: list[dict] = []  # 淇濆瓨鏈嶅姟鎻愪緵鐨勫伐鍏峰畾涔夈€?        self._handlers: dict[str, callable] = {}  # 淇濆瓨鍘熷宸ュ叿鍚嶅埌澶勭悊鍣ㄧ殑鏄犲皠銆?
    def register(self, tool_defs: list[dict],  # 鍚?MCP 瀹㈡埛绔敞鍐屽伐鍏峰畾涔夊拰澶勭悊鍣紱鏈€鏃╋細14.171
                 handlers: dict[str, callable]):  # 鎺ユ敹宸ュ叿瀹氫箟鍜屽搴斿鐞嗗櫒銆?        names = [tool.get("name") for tool in tool_defs]  # 鍏堟彁鍙栧悕绉帮紝鍚庣画鎵€鏈夋牎楠岄兘浠ユ湇鍔＄鍘熷宸ュ叿鏍囪瘑涓哄噯銆?        if any(not isinstance(name, str) or not name for name in names):  # 绌哄悕绉版棤娉曠敓鎴愮ǔ瀹氱殑妯″瀷宸ュ叿鍚嶃€?            raise ValueError("姣忎釜 MCP 宸ュ叿閮藉繀椤诲叿鏈夐潪绌哄悕绉?)  # 缂哄皯鏈夋晥鍚嶇О鏃舵嫆缁濇敞鍐屻€?        if len(set(names)) != len(names):  # 鍚屼竴鏈嶅姟鍐呴噸鍚嶄細浣?handler 鍒嗗彂浜х敓姝т箟銆?            raise ValueError(f"MCP 鏈嶅姟 {self.name!r} 涓瓨鍦ㄩ噸澶嶅伐鍏峰悕绉?)  # 閲嶅悕鏃舵嫆缁濇敞鍐屻€?        missing = [name for name in names if name not in handlers]  # schema 鍙浣嗕笉鍙墽琛屼細鍦ㄦā鍨嬭皟鐢ㄥ悗鎵嶅け璐ワ紝杩炴帴鏃跺簲鎻愬墠鎷掔粷銆?        if missing:  # 妫€鏌ユ槸鍚︾己灏戝鐞嗗櫒銆?            raise ValueError(f"缂哄皯 MCP 宸ュ叿澶勭悊鍣細{', '.join(missing)}")  # 鎶ュ憡缂哄け鐨勫鐞嗗櫒銆?        self.tools = list(tool_defs)  # 鏍￠獙閫氳繃鍚庡啀鏁翠綋鍙戝竷锛岄伩鍏嶅鎴风澶勪簬鍗婃敞鍐岀姸鎬併€?        self._handlers = dict(handlers)  # 澶嶅埗鏄犲皠锛岄槻姝㈣皟鐢ㄦ柟鍚庣画淇敼鍘熷瓧鍏稿奖鍝嶅凡杩炴帴鏈嶅姟銆?
    def call_tool(self, tool_name: str, args: dict) -> str:  # 璋冪敤 MCP 宸ュ叿骞剁粺涓€杩斿洖鏂囨湰缁撴灉锛涙渶鏃╋細14.183
        handler = self._handlers.get(tool_name)  # 妯″瀷渚т娇鐢ㄥ墠缂€鍚嶏紝闂寘浼氬湪杩涘叆杩欓噷鍓嶈繕鍘熸湇鍔＄鍘熷悕銆?        if not handler:  # 鏈煡宸ュ叿浣滀负鏅€氱粨鏋滆繑鍥烇紝淇濇寔涓?Agent 宸ュ叿鍙嶉閾惧畬鏁淬€?            return f"MCP 閿欒锛氭湭鐭ュ伐鍏封€渰tool_name}鈥?  # 杩斿洖鏈煡宸ュ叿閿欒銆?        try:  # 妯℃嫙鐪熷疄 MCP RPC 杈圭晫锛屾妸杩滅鏁呴殰闅旂涓烘枃鏈粨鏋溿€?            return str(handler(**args))  # 缁熶竴鏂囨湰鍖栵紝鍜屽唴缃伐鍏峰叡浜浉鍚岀殑 tool_result 鍗忚銆?        except Exception as exc:  # 鎹曡幏澶勭悊鍣ㄦ墽琛屽紓甯搞€?            return f"MCP 閿欒锛歿type(exc).__name__}锛歿exc}"  # 鎶婂紓甯歌浆鎹负宸ュ叿缁撴灉銆?

mcp_clients: dict[str, MCPClient] = {}  # 淇濆瓨宸茶繛鎺ョ殑 MCP 瀹㈡埛绔€?_DISALLOWED_CHARS = re.compile(r"[^a-zA-Z0-9_-]")  # 鍖归厤宸ュ叿鍚嶄腑涓嶅厑璁哥殑瀛楃銆?
# Authorization comes from host configuration, never server descriptions.锝滀腑鏂囷細鎺堟潈浠呮潵鑷涓婚厤缃紝缁濅笉閲囦俊鏈嶅姟绔弿杩般€?MCP_HOST_POLICY = {  # 瀹夸富涓烘湇鍔″拰宸ュ叿閰嶇疆鏉冮檺銆?    ("docs", "search"): "allow",  # 鍏佽鏂囨。鎼滅储銆?    ("docs", "get_version"): "allow",  # 鍏佽璇诲彇鏂囨。鐗堟湰銆?    ("deploy", "status"): "allow",  # 鍏佽鏌ヨ閮ㄧ讲鐘舵€併€?    ("deploy", "trigger"): "confirm",  # 瑙﹀彂閮ㄧ讲鍓嶉渶瑕佺‘璁ゃ€?}  # 缁撴潫瀹夸富绛栫暐琛ㄣ€?

def normalize_mcp_name(name: str) -> str:  # 瑙勮寖鍖?MCP 鏈嶅姟鍚嶇О锛涙渶鏃╋細14.206 鈭?    """Replace characters outside the model tool-name alphabet.锝滀腑鏂囷細鏇挎崲涓嶇鍚堟ā鍨嬪伐鍏峰懡鍚嶅瓧绗﹂泦鐨勫瓧绗︺€?""
    normalized = _DISALLOWED_CHARS.sub("_", name)  # 灏嗕笉鍏佽鐨勫瓧绗︽浛鎹负涓嬪垝绾裤€?    if not normalized:  # 妫€鏌ヨ鑼冨寲鍚庣殑鍚嶇О銆?        raise ValueError("MCP 鍚嶇О瑙勮寖鍖栧悗涓嶈兘涓虹┖瀛楃涓?)  # 绌哄悕绉版棤娉曚綔涓哄伐鍏峰悕銆?    return normalized  # 杩斿洖瑙勮寖鍖栧悕绉般€?

def _mock_server_docs() -> MCPClient:  # 鏋勯€犵ず渚嬫枃妗?MCP 鏈嶅姟锛涙渶鏃╋細14.214 鈭?    client = MCPClient("docs")  # 鍒涘缓鏂囨。妯℃嫙瀹㈡埛绔€?    client.register(  # 娉ㄥ唽绀轰緥宸ュ叿鍜屽鐞嗗櫒銆?        tool_defs=[  # 寮€濮嬪畾涔夋枃妗ｅ伐鍏枫€?            {"name": "search", "description": "鎼滅储鏂囨。銆?,  # 瀹氫箟鎼滅储宸ュ叿鍙婃弿杩般€?             "inputSchema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                             "properties": {"query": {"type": "string"}},  # 瀹氫箟瀛楃涓叉煡璇㈠弬鏁般€?                             "required": ["query"]},  # 鏌ヨ鍙傛暟蹇呭～銆?             "annotations": {"readOnlyHint": True}},  # 鏈嶅姟绔彁绀鸿宸ュ叿鍙銆?            {"name": "get_version",  # 瀹氫箟鐗堟湰鏌ヨ宸ュ叿銆?             "description": "鑾峰彇鏂囨。 API 鐨勭増鏈€?,  # 鎻忚堪宸ュ叿鐢ㄩ€斻€?             "inputSchema": {"type": "object", "properties": {},  # 澹版槑鏃犲睘鎬х殑瀵硅薄杈撳叆銆?                             "required": []},  # 涓嶈姹傝緭鍏ュ弬鏁般€?             "annotations": {"readOnlyHint": True}},  # 鏈嶅姟绔彁绀鸿宸ュ叿鍙銆?        ],  # 缁撴潫宸ュ叿瀹氫箟鍒楄〃銆?        handlers={  # 寮€濮嬫彁渚涘伐鍏峰鐞嗗櫒銆?            "search": lambda query: f"[docs] Found 3 results for '{query}'",  # 妯℃嫙鎼滅储骞惰繑鍥炲浐瀹氭枃鏈€?            "get_version": lambda: "[docs] API v2.1.0",  # 妯℃嫙杩斿洖 API 鐗堟湰銆?        })  # 瀹屾垚娉ㄥ唽銆?    return client  # 杩斿洖閰嶇疆濂界殑瀹㈡埛绔€?

def _mock_server_deploy() -> MCPClient:  # 鏋勯€犵ず渚嬮儴缃?MCP 鏈嶅姟锛涙渶鏃╋細14.243 鈭?    client = MCPClient("deploy")  # 鍒涘缓閮ㄧ讲妯℃嫙瀹㈡埛绔€?    client.register(  # 娉ㄥ唽閮ㄧ讲宸ュ叿鍜屽鐞嗗櫒銆?        tool_defs=[  # 寮€濮嬪畾涔夐儴缃插伐鍏枫€?            {"name": "trigger",  # 瀹氫箟瑙﹀彂閮ㄧ讲宸ュ叿銆?             "description": "瑙﹀彂涓€娆￠儴缃层€?,  # 鎻忚堪宸ュ叿鐢ㄩ€斻€?             "inputSchema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                             "properties": {"service": {"type": "string"}},  # 瀹氫箟鏈嶅姟鍚嶇О鍙傛暟銆?                             "required": ["service"]},  # 鏈嶅姟鍚嶇О蹇呭～銆?             "annotations": {"destructiveHint": True}},  # 鏈嶅姟绔彁绀烘搷浣滃叿鏈夌牬鍧忔€с€?            {"name": "status", "description": "妫€鏌ラ儴缃茬姸鎬併€?,  # 瀹氫箟閮ㄧ讲鐘舵€佹煡璇㈠伐鍏枫€?             "inputSchema": {"type": "object",  # 澹版槑瀵硅薄绫诲瀷杈撳叆銆?                             "properties": {"service": {"type": "string"}},  # 瀹氫箟鏈嶅姟鍚嶇О鍙傛暟銆?                             "required": ["service"]},  # 鏈嶅姟鍚嶇О蹇呭～銆?             "annotations": {"readOnlyHint": True}},  # 鏈嶅姟绔彁绀鸿宸ュ叿鍙銆?        ],  # 缁撴潫宸ュ叿瀹氫箟鍒楄〃銆?        handlers={  # 寮€濮嬫彁渚涘伐鍏峰鐞嗗櫒銆?            "trigger": lambda service: f"[deploy] Triggered: {service}",  # 妯℃嫙瑙﹀彂閮ㄧ讲骞惰繑鍥炴枃鏈€?            "status": lambda service: f"[deploy] {service}: running (v1.4.2)",  # 妯℃嫙杩斿洖閮ㄧ讲鐘舵€併€?        })  # 瀹屾垚娉ㄥ唽銆?    return client  # 杩斿洖閰嶇疆濂界殑瀹㈡埛绔€?

MOCK_SERVERS = {  # 灏嗗厑璁歌繛鎺ョ殑鍚嶇О鏄犲皠鍒板伐鍘傚嚱鏁般€?    "docs": _mock_server_docs,  # 娉ㄥ唽鏂囨。妯℃嫙鏈嶅姟銆?    "deploy": _mock_server_deploy,  # 娉ㄥ唽閮ㄧ讲妯℃嫙鏈嶅姟銆?}  # 缁撴潫鏈嶅姟宸ュ巶琛ㄣ€?

def connect_mcp(name: str) -> str:  # 鎸夌櫧鍚嶅崟杩炴帴 MCP 鏈嶅姟锛涙渶鏃╋細14.282
    if name in mcp_clients:  # 杩炴帴鏄箓绛夋搷浣滐紝閲嶅璋冪敤涓嶈兘閲嶅缓瀹㈡埛绔苟鏀瑰彉宸叉毚闇插伐鍏枫€?        return f"MCP 鏈嶅姟鈥渰name}鈥濆凡缁忚繛鎺?  # 宸茶繛鎺ユ椂鐩存帴杩斿洖銆?    factory = MOCK_SERVERS.get(name)  # 鎸夊悕绉版煡鎵惧厑璁哥殑鏈嶅姟宸ュ巶銆?    if not factory:  # 娌℃湁瀵瑰簲宸ュ巶鏃舵嫆缁濊繛鎺ャ€?        available = ", ".join(MOCK_SERVERS)  # 鍒楀嚭鍙繛鎺ョ殑鏈嶅姟銆?        return f"鏈煡 MCP 鏈嶅姟鈥渰name}鈥濄€傚彲鐢ㄦ湇鍔★細{available}"  # 杩斿洖鏈煡鏈嶅姟鎻愮ず銆?    mcp_client = factory()  # 宸ュ巶璐熻矗鍙戠幇宸ュ叿骞跺缓绔嬪疄闄呰皟鐢ㄥ鐞嗗櫒銆?    mcp_clients[name] = mcp_client  # 娉ㄥ唽鍚庯紝涓嬩竴杞?assemble_tool_pool 鎵嶄細鎶婂伐鍏锋毚闇茬粰妯″瀷銆?    tool_names = [tool["name"] for tool in mcp_client.tools]  # 鎻愬彇宸插彂鐜扮殑鍘熷宸ュ叿鍚嶃€?    print(f"  \033[31m[mcp] connected: {name} -> {tool_names}\033[0m")  # 鍦ㄧ粓绔樉绀鸿繛鎺ョ粨鏋溿€?    return (f"宸茶繛鎺?MCP 鏈嶅姟鈥渰name}鈥濄€?  # 杩斿洖杩炴帴鎴愬姛淇℃伅銆?            f"鍙戠幇 {len(mcp_client.tools)} 涓伐鍏凤細{', '.join(tool_names)}")  # 闄勪笂宸ュ叿鏁伴噺鍜屽悕绉般€?

def assemble_tool_pool() -> tuple[list[dict], dict]:  # 鍚堝苟鍐呯疆宸ュ叿鍜屽凡杩炴帴 MCP 宸ュ叿锛涙渶鏃╋細14.316 鈭?    """Merge builtin tools + all MCP tools into one pool.锝滀腑鏂囷細鎶婂唴缃伐鍏峰拰鍏ㄩ儴 MCP 宸ュ叿鍚堝苟涓虹粺涓€宸ュ叿姹犮€?""
    global mcp_tool_policies  # 澹版槑灏嗘洿鏂板叏灞€ MCP 鏉冮檺琛ㄣ€?    tools = list(BUILTIN_TOOLS)  # 姣忚疆浠庡唴缃畾涔夊鍒讹紝閬垮厤鍔ㄦ€?MCP 宸ュ叿姘镐箙淇敼鍏ㄥ眬鍩虹琛ㄣ€?    handlers = dict(BUILTIN_HANDLERS)  # schema 涓庡鐞嗗櫒鍚屾閲嶅缓锛屼繚璇佹ā鍨嬪彲瑙佸伐鍏蜂竴瀹氭湁鎵ц鍏ュ彛銆?    policies: dict[str, str] = {}  # 鏉冮檺鏉ヨ嚜瀹夸富鐧藉悕鍗曪紝缁濅笉閲囩敤鏈嶅姟绔嚜鎶ョ殑 annotations 浣滀负鎺堟潈銆?    origins = {tool["name"]: f"built-in tool {tool['name']!r}"  # 鍏堣褰曞唴缃伐鍏峰悕绉板拰鏉ユ簮銆?               for tool in tools}  # 鐢ㄤ簬妫€娴嬪姩鎬佸伐鍏峰悕绉板啿绐併€?    for server_name, mcp_client in mcp_clients.items():  # 宸茶繛鎺ユ湇鍔℃槸鍔ㄦ€佹潵婧愶紝姣忚疆閮介噸鏂板悎骞跺叾褰撳墠宸ュ叿鐩綍銆?        safe_server = normalize_mcp_name(server_name)  # 鏈嶅姟鍚嶅厛瑙勮寖鍖栵紝纭繚婊¤冻妯″瀷 API 鐨勫伐鍏峰懡鍚嶉檺鍒躲€?        for tool_def in mcp_client.tools:  # 閬嶅巻鏈嶅姟鎻愪緵鐨勫伐鍏枫€?            raw_name = tool_def["name"]  # 璇诲彇鏈嶅姟绔師濮嬪伐鍏峰悕銆?            safe_tool = normalize_mcp_name(raw_name)  # 瑙勮寖鍖栧伐鍏峰悕銆?            prefixed = f"mcp__{safe_server}__{safe_tool}"  # 鍙岄噸鍓嶇紑淇濈暀鏉ユ簮骞堕殧绂讳笉鍚屾湇鍔＄殑鍚屽悕宸ュ叿銆?            if len(prefixed) > 64:  # 妫€鏌ユā鍨嬪伐鍏峰悕闀垮害闄愬埗銆?                raise ValueError(  # 鍚嶇О杩囬暱鏃舵姏鍑洪敊璇€?                    f"MCP tool name is longer than 64 characters: {prefixed}"  # 閿欒涓寘鍚敓鎴愮殑宸ュ叿鍚嶃€?                )  # 缁撴潫寮傚父鏋勯€犮€?            origin = f"MCP tool {server_name!r}/{raw_name!r}"  # 璁板綍宸ュ叿鎵€灞炴湇鍔″強鍘熷悕銆?            if prefixed in origins :  # 瑙勮寖鍖栧彲鑳芥妸涓嶅悓鍘熷悕鎶樺彔鎴愬悓涓€瀛楃涓诧紝蹇呴』鏄惧紡妫€娴嬭€岄潪闈欓粯瑕嗙洊銆?                raise ValueError(  # 妫€娴嬪埌鍐茬獊鏃舵姏鍑洪敊璇€?                    "MCP tool name collision after normalization: "  # 璇存槑鍐茬獊鐢辫鑼冨寲寮曡捣銆?                    f"{prefixed!r} maps both {origins[prefixed]} and {origin}"  # 鍒楀嚭鍐茬獊鍚嶇О鍜屼袱涓潵婧愩€?                )  # 缁撴潫寮傚父鏋勯€犮€?            schema = tool_def.get("inputSchema", {})  # MCP 浣跨敤 inputSchema锛屼富妯″瀷鎺ュ彛浣跨敤 input_schema锛屽悎骞舵椂瀹屾垚鍗忚閫傞厤銆?            if not isinstance(schema, dict) or schema.get("type", "object") != "object":  # 杈撳叆 schema 蹇呴』鏄璞″畾涔夈€?                raise ValueError(f"Invalid input schema for {origin}")  # 鏃犳晥鏃舵嫆缁濈粍瑁呫€?            origins[prefixed] = origin  # 淇濆瓨鏉ユ簮鐢ㄤ簬鍚庣画纰版挒鎶ラ敊锛屾彁鍗囧姩鎬佸伐鍏烽棶棰樼殑鍙瘖鏂€с€?            tools.append({  # 鍚戞ā鍨嬪伐鍏峰垪琛ㄨ拷鍔犻€傞厤鍚庣殑瀹氫箟銆?                "name": prefixed,  # 浣跨敤甯︽湇鍔″墠缂€鐨勫悕绉般€?                "description": tool_def.get("description", ""),  # 淇濈暀宸ュ叿鎻忚堪銆?                "input_schema": schema,  # 杞崲杈撳叆 schema 瀛楁鍚嶃€?            })  # 瀹屾垚宸ュ叿瀹氫箟銆?            handlers[prefixed] = (  # 榛樿鍙傛暟鍦ㄥ垱寤洪棴鍖呮椂鍐荤粨瀹㈡埛绔拰鍘熷伐鍏峰悕锛岄伩鍏嶅惊鐜彉閲忔櫄缁戝畾閿欒銆?                lambda *, client=mcp_client, tool=raw_name, **kwargs:  # 缁戝畾褰撳墠瀹㈡埛绔拰鍘熷宸ュ叿鍚嶃€?                client.call_tool(tool, kwargs)  # 璋冪敤瀵瑰簲瀹㈡埛绔苟浼犲叆妯″瀷鍙傛暟銆?            )  # 瀹屾垚澶勭悊鍣ㄩ棴鍖呫€?            policies[prefixed] = MCP_HOST_POLICY.get(  # 鏈垪鍏ュ涓荤櫧鍚嶅崟鐨勮繙绔兘鍔涢粯璁よ姹傜敤鎴风‘璁ゃ€?                (server_name, raw_name), "confirm"  # 鏈厤缃椂榛樿瑕佹眰纭銆?            )  # 瀹屾垚璇ュ伐鍏风殑鏉冮檺鏄犲皠銆?    mcp_tool_policies = policies  # 涓庡伐鍏锋睜涓€璧峰師瀛愬埛鏂帮紝鏉冮檺閽╁瓙鐪嬪埌鐨勫悕绉板拰鏈疆 schema 淇濇寔涓€鑷淬€?    return tools, handlers  # 涓诲惊鐜彧鎺ユ敹缁熶竴姹狅紝鏃犻渶鍖哄垎鍐呯疆璋冪敤涓?MCP 璋冪敤銆?

# -- Lead Worktree Tools --锝淟ead 宸ヤ綔鏍戝伐鍏凤細缁ф壙绗?13 绔狅紝璁╀富 Agent 涓轰换鍔″垱寤洪殧绂诲伐浣滃尯銆?
def run_create_worktree(name: str, task_id: str) -> str:  # 涓?Lead 鎸囧畾浠诲姟鍒涘缓宸ヤ綔鏍戯紱鏈€鏃╋細13.1501
    return create_worktree(name, task_id)

# -- Basic Tool Handlers --锝滃熀纭€宸ュ叿澶勭悊鍣細姹囨€荤 2銆?銆?0銆?3銆?4 绔犵殑宸ュ叿瀹炵幇骞剁粺涓€閫傞厤璋冪敤銆?
def run_create_task(subject: str, description: str = "") -> str:  # 澶勭悊妯″瀷鐨勫垱寤轰换鍔¤皟鐢紱鏈€鏃╋細10.341 鈭?    task = create_task(subject, description)  # 鍒涘缓骞舵寔涔呭寲浠诲姟銆?    print(f"  \033[34m[create] {task.subject}\033[0m")  # 鍦ㄧ粓绔樉绀轰换鍔′富棰樸€?    return f"Created {task.id}: {task.subject}"  # 鍚戞ā鍨嬭繑鍥炵敓鎴愮殑浠诲姟 ID 鍜屼富棰樸€?

def run_update_task(task_id: str, addBlockedBy: list[str]) -> str:  # 澶勭悊妯″瀷鐨勪换鍔′緷璧栨洿鏂拌皟鐢紱鏈€鏃╋細10.347 鈭?    try:  # 灏嗗父瑙佽緭鍏ュ拰鏌ユ壘閿欒杞负鏂囨湰銆?        task = update_task(task_id, addBlockedBy)  # 鏍￠獙骞惰拷鍔犱换鍔′緷璧栥€?    except ValueError as exc:  # 渚濊禆鎴栧弬鏁版棤鏁堟椂銆?        return f"Error: {exc}"  # 杩斿洖鏍￠獙閿欒銆?    except FileNotFoundError:  # 浠诲姟鏂囦欢涓嶅瓨鍦ㄦ椂銆?        return f"Error: Task {task_id} not found"  # 杩斿洖浠诲姟鏈壘鍒版彁绀恒€?    dependencies = ", ".join(task.blockedBy) or "(none)"  # 鏁寸悊浠诲姟褰撳墠鐨勪緷璧?ID銆?    print(f"  \033[34m[update] {task.subject} blockedBy: {dependencies}\033[0m")  # 鍦ㄧ粓绔樉绀烘洿鏂扮粨鏋溿€?    return f"Updated {task.id} blockedBy: {dependencies}"  # 鍚戞ā鍨嬭繑鍥炴洿鏂板悗鐨勪緷璧栥€?

def run_list_tasks() -> str:  # 澶勭悊妯″瀷鐨勪换鍔″垪琛ㄨ皟鐢紱鏈€鏃╋細10.354 鈭?    tasks = list_tasks()  # 璇诲彇鎸佷箙鍖栦换鍔″垪琛ㄣ€?    if not tasks:  # 娌℃湁浠诲姟鏃躲€?        return "No tasks."  # 杩斿洖绌哄垪琛ㄦ彁绀恒€?    return "\n".join(  # 灏嗕换鍔′俊鎭嫾鎴愬琛屻€?        f"  {t.id}: {t.subject} [{t.status}]"  # 鏄剧ず浠诲姟 ID銆佷富棰樺拰鐘舵€併€?        + (f" (wt:{t.worktree})" if t.worktree else "")  # 宸茬粦瀹氬伐浣滄爲鏃堕檮涓婂悕绉般€?        for t in tasks)  # 閬嶅巻鎵€鏈変换鍔°€?

def run_get_task(task_id: str) -> str:  # 澶勭悊妯″瀷鐨勫崟浠诲姟鏌ヨ璋冪敤锛涙渶鏃╋細10.377 鈭?    try:  # 鏌ヨ鎸囧畾浠诲姟骞跺鐞嗗父瑙侀敊璇€?        return get_task_json(task_id)  # 杩斿洖浠诲姟鐨?JSON 鏂囨湰銆?    except ValueError as exc:  # 浠诲姟 ID 鎴栧唴瀹规棤鏁堟椂銆?        return f"Error: {exc}"  # 杩斿洖鏍￠獙閿欒銆?    except FileNotFoundError:  # 浠诲姟鏂囦欢涓嶅瓨鍦ㄦ椂銆?        return f"Error: task {task_id} not found"  # 杩斿洖鏈壘鍒版彁绀恒€?
def run_claim_task(task_id: str) -> str:  # 澶勭悊 Lead 鐨勪换鍔¤棰嗚皟鐢紱鏈€鏃╋細10.381 鈭?    try:  # 浠?Lead 韬唤棰嗗彇浠诲姟骞跺鐞嗗父瑙侀敊璇€?        return claim_task(task_id, owner="agent")  # 浣跨敤 agent 浣滀负璐熻矗浜恒€?    except ValueError as exc:  # 浠诲姟 ID 鎴栧唴瀹规棤鏁堟椂銆?        return f"Error: {exc}"  # 杩斿洖鏍￠獙閿欒銆?    except FileNotFoundError:  # 浠诲姟鏂囦欢涓嶅瓨鍦ㄦ椂銆?        return f"Error: task {task_id} not found"  # 杩斿洖鏈壘鍒版彁绀恒€?
def run_complete_task(task_id: str) -> str:  # 澶勭悊 Lead 鐨勪换鍔″畬鎴愯皟鐢紱鏈€鏃╋細10.385 鈭?    try:  # 浠?Lead 韬唤瀹屾垚浠诲姟骞跺鐞嗗父瑙侀敊璇€?        return complete_task(task_id, owner="agent")  # 鍙厑璁?agent 瀹屾垚鑷繁棰嗗彇鐨勪换鍔°€?    except ValueError as exc:  # 浠诲姟 ID 鎴栧唴瀹规棤鏁堟椂銆?        return f"Error: {exc}"  # 杩斿洖鏍￠獙閿欒銆?    except FileNotFoundError:  # 浠诲姟鏂囦欢涓嶅瓨鍦ㄦ椂銆?        return f"Error: task {task_id} not found"  # 杩斿洖鏈壘鍒版彁绀恒€?
def run_spawn_teammate(name: str, role: str, prompt: str,  # 澶勭悊妯″瀷鐨勯槦鍙嬪惎鍔ㄨ皟鐢紱鏈€鏃╋細13.1425 鈭?                       task_id: str | None = None,  # 鍙€夊湴涓洪槦鍙嬫寚瀹氫换鍔°€?                       require_plan: bool = False) -> str:  # 鍙€夊湴瑕佹眰闃熷弸鍏堟彁浜よ鍒掋€?    return spawn_teammate_thread(name, role, prompt, task_id, require_plan)  # 灏嗗弬鏁颁氦缁欓槦鍙嬬嚎绋嬪惎鍔ㄥ嚱鏁般€?

def run_list_teammates() -> str:  # 鍒楀嚭闃熷弸绾跨▼鍙婁换鍔＄姸鎬侊紱鏈€鏃╋細13.1431 鈭?    with team_lock:  # 鎸侀攣璇诲彇娲昏穬闃熷弸鐘舵€併€?        if not active_teammates:  # 娌℃湁娲昏穬闃熷弸鏃躲€?            return "No active teammates."  # 杩斿洖绌哄垪琛ㄦ彁绀恒€?        return "\n".join(  # 灏嗛槦鍙嬩俊鎭嫾鎴愬琛屻€?            f"{name}: {status}"  # 鏄剧ず闃熷弸鍚嶇О鍜屽綋鍓嶇姸鎬併€?            for name, status in sorted(active_teammates.items())  # 鎸夊悕绉版帓搴忓苟閬嶅巻闃熷弸銆?        )  # 杩斿洖鏍煎紡鍖栫粨鏋溿€?

def run_send_message(to: str, content: str) -> str:  # 澶勭悊 Lead 鐨勫洟闃熸秷鎭彂閫佽皟鐢紱鏈€鏃╋細13.1441 鈭?    if to not in active_teammates:  # 鍏堟鏌ユ帴鏀堕槦鍙嬫槸鍚︽椿璺冦€?        return f"Teammate '{to}' is not active"  # 涓嶅瓨鍦ㄦ椂杩斿洖鎻愮ず銆?    BUS.send("lead", to, content)  # 浠?lead 韬唤鍚戦槦鍙嬮偖绠卞彂閫佹秷鎭€?    return f"Sent to {to}"  # 杩斿洖鍙戦€佹垚鍔熸彁绀恒€?
def run_connect_mcp(name: str) -> str:  # 澶勭悊妯″瀷鐨?MCP 杩炴帴璋冪敤锛涙渶鏃╋細14.298 鈭?    return connect_mcp(name)  # 璋冪敤 MCP 鏈嶅姟杩炴帴鍑芥暟骞惰繑鍥炵粨鏋溿€?

# -- Tool Definitions --锝滃伐鍏峰畾涔夛細缁ф壙绗?2 绔犵殑 schema/handler 鍙岃〃锛屽苟姹囨€荤 5鈥?4 绔犳柊澧炶兘鍔涖€?
# The model sees tool schemas; Python executes handlers. S15 keeps both tables锝滀腑鏂囷細妯″瀷璇诲彇宸ュ叿 schema锛孭ython 鎵ц澶勭悊鍣紱绗?15 绔犳樉寮忎繚鐣欎袱寮犺〃锛?# explicit so every added capability is visible in one place.锝滀腑鏂囷細浣挎墍鏈夋柊澧炶兘鍔涢兘鑳藉湪鍚屼竴澶勬煡鐪嬨€?BUILTIN_TOOLS = [
    {"name": "bash", "description": "杩愯涓€鏉?Shell 鍛戒护銆?,
     "input_schema": {"type": "object",
                      "properties": {"command": {"type": "string"},
                                     "run_in_background": {"type": "boolean"}},
                      "required": ["command"]}},
    {"name": "read_file", "description": "璇诲彇鏂囦欢鍐呭銆?,
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "limit": {"type": "integer"},
                                     "offset": {"type": "integer"}},
                      "required": ["path"]}},
    {"name": "write_file", "description": "鎶婂唴瀹瑰啓鍏ユ枃浠躲€?,
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "description": "鍦ㄦ枃浠朵腑绮剧‘鏇挎崲涓€娆℃寚瀹氭枃鏈€?,
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "old_text": {"type": "string"},
                                     "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "鏌ユ壘绗﹀悎 glob 妯″紡鐨勬枃浠讹紱** 琛ㄧず閫掑綊鍖归厤銆?,
     "input_schema": {"type": "object",
                      "properties": {"pattern": {"type": "string"}},
                      "required": ["pattern"]}},
    {"name": "todo_write",
     "description": "鍒涘缓骞剁鐞嗗綋鍓嶄細璇濈殑寰呭姙鍒楄〃銆?,
     "input_schema": {"type": "object",
                      "properties": {"todos": {"type": "array",
                          "items": {"type": "object",
                                    "properties": {
                                        "content": {"type": "string"},
                                        "status": {"type": "string",
                                                   "enum": ["pending", "in_progress", "completed"]}},
                                    "required": ["content", "status"]}}},
                      "required": ["todos"]}},
    {"name": "task",
     "description": "鍚姩涓€涓笓娉ㄥ鐞嗗崟椤瑰伐浣滅殑瀛?Agent锛屽苟鍙繑鍥炲叾鏈€缁堟€荤粨銆?,
     "input_schema": {"type": "object",
                      "properties": {"description": {"type": "string"}},
                      "required": ["description"]}},
    {"name": "load_skill",
     "description": "鎸夊悕绉板姞杞芥煇椤规妧鑳界殑瀹屾暣鍐呭銆?,
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"}},
                      "required": ["name"]}},
    {"name": "compact",
     "description": "鎬荤粨姝ゅ墠瀵硅瘽锛屽苟浣跨敤鍘嬬缉鍚庣殑涓婁笅鏂囩户缁伐浣溿€?,
     "input_schema": {"type": "object",
                      "properties": {"focus": {"type": "string"}},
                      "required": []}},
    {"name": "create_task",
     "description": "鍒涘缓浠诲姟骞惰繑鍥炶繍琛屾椂鐢熸垚鐨勪换鍔?ID銆?,
     "input_schema": {"type": "object",
                      "properties": {"subject": {"type": "string"},
                                     "description": {"type": "string"}},
                      "required": ["subject"],
                      "additionalProperties": False}},
    {"name": "update_task",
     "description": "浣跨敤 create_task 杩斿洖鐨勪换鍔?ID 娣诲姞渚濊禆鍏崇郴銆?,
     "input_schema": {"type": "object",
                      "properties": {
                          "task_id": {"type": "string",
                                      "pattern": "^task_[0-9a-f]{8}$"},
                          "addBlockedBy": {
                              "type": "array",
                              "items": {"type": "string",
                                        "pattern": "^task_[0-9a-f]{8}$"},
                              "minItems": 1}},
                      "required": ["task_id", "addBlockedBy"],
                      "additionalProperties": False}},
    {"name": "list_tasks", "description": "鍒楀嚭鍏ㄩ儴浠诲姟銆?,
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_task", "description": "鑾峰彇浠诲姟鐨勫畬鏁磋鎯呫€?,
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "claim_task", "description": "璁ら涓€涓緟澶勭悊浠诲姟銆?,
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "complete_task", "description": "瀹屾垚涓€涓繘琛屼腑鐨勪换鍔°€?,
     "input_schema": {"type": "object",
                      "properties": {"task_id": {"type": "string"}},
                      "required": ["task_id"]}},
    {"name": "schedule_cron",
     "description": ("鍒涘缓 Cron 瀹氭椂浠诲姟銆俢ron 浣跨敤浜旀鏍煎紡锛氬垎閽熴€佸皬鏃躲€佹湀涓棩鏈熴€?
                     "鏈堜唤銆佹槦鏈熴€備竴娆℃€ф彁閱掑簲璁＄畻鐩爣鍒嗛挓锛屽苟璁剧疆 recurring=false銆?),
     "input_schema": {"type": "object",
                      "properties": {"cron": {"type": "string"},
                                     "prompt": {"type": "string"},
                                     "recurring": {"type": "boolean"},
                                     "durable": {"type": "boolean"}},
                      "required": ["cron", "prompt"]}},
    {"name": "list_crons", "description": "鍒楀嚭宸茬櫥璁扮殑 Cron 瀹氭椂浠诲姟銆?,
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "cancel_cron", "description": "鏍规嵁浠诲姟 ID 鍙栨秷 Cron 瀹氭椂浠诲姟銆?,
     "input_schema": {"type": "object",
                      "properties": {"job_id": {"type": "string"}},
                      "required": ["job_id"]}},
    {"name": "spawn_teammate", "description": "鍚姩涓€涓彲鎸佺画鎺ユ敹宸ヤ綔鐨勯槦鍙嬨€?,
     "input_schema": {"type": "object",
                      "properties": {"name": {
                                         "type": "string",
                                         "pattern": "^[A-Za-z0-9_-]{1,64}$",
                                     },
                                     "role": {"type": "string"},
                                     "prompt": {"type": "string"},
                                     "task_id": {
                                         "type": "string",
                                         "pattern": "^task_[0-9a-f]{8}$",
                                     },
                                     "require_plan": {"type": "boolean"}},
                      "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "鍒楀嚭褰撳墠娲昏穬鐨勯槦鍙嬨€?,
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "send_message", "description": "鍚戦槦鍙嬪彂閫佹秷鎭€?,
     "input_schema": {"type": "object",
                      "properties": {"to": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["to", "content"]}},
    {"name": "request_shutdown",
     "description": "璇锋眰鎸囧畾闃熷弸瀹夊叏鍏抽棴銆?,
     "input_schema": {"type": "object",
                      "properties": {"teammate": {"type": "string"}},
                      "required": ["teammate"]}},
    {"name": "request_plan",
     "description": "瑕佹眰鎸囧畾闃熷弸鎻愪氦璁″垝銆?,
     "input_schema": {"type": "object",
                      "properties": {"teammate": {"type": "string"},
                                     "task": {"type": "string"}},
                      "required": ["teammate", "task"]}},
    {"name": "review_plan",
     "description": "鎵瑰噯鎴栨嫆缁濋槦鍙嬫彁浜ょ殑璁″垝銆?,
     "input_schema": {"type": "object",
                      "properties": {"request_id": {"type": "string"},
                                     "approve": {"type": "boolean"},
                                     "feedback": {"type": "string"}},
                      "required": ["request_id", "approve"]}},
    {"name": "create_worktree",
     "description": "涓哄緟澶勭悊浠诲姟鍒涘缓涓庡叾缁戝畾鐨?Git worktree銆?,
     "input_schema": {"type": "object",
                      "properties": {"name": {
                                         "type": "string",
                                         "pattern": ("^(?!.*\\.\\.)[A-Za-z0-9]"
                                                     "[A-Za-z0-9._-]{0,63}$"),
                                         "maxLength": 64,
                                     },
                                     "task_id": {"type": "string"}},
                      "required": ["name", "task_id"],
                      "additionalProperties": False}},
    {"name": "connect_mcp",
     "description": "杩炴帴 MCP 鏈嶅姟锛坉ocs 鎴?deploy锛夊苟鍙戠幇鍏朵腑鐨勫伐鍏枫€?,
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"}},
                      "required": ["name"]}},
]

BUILTIN_HANDLERS = {
    "bash": run_agent_bash,
    "read_file": run_agent_read,
    "write_file": run_agent_write,
    "edit_file": run_agent_edit,
    "glob": run_agent_glob,
    "todo_write": run_todo_write, "task": spawn_subagent,
    "load_skill": load_skill,
    "create_task": run_create_task, "update_task": run_update_task,
    "list_tasks": run_list_tasks,
    "get_task": run_get_task,
    "claim_task": run_claim_task, "complete_task": run_complete_task,
    "schedule_cron": run_schedule_cron,
    "list_crons": run_list_crons,
    "cancel_cron": run_cancel_cron,
    "spawn_teammate": run_spawn_teammate,
    "list_teammates": run_list_teammates,
    "send_message": run_send_message,
    "request_shutdown": run_request_shutdown,
    "request_plan": run_request_plan, "review_plan": run_review_plan,
    "create_worktree": run_create_worktree,
    "connect_mcp": run_connect_mcp,
}


# -- Context --锝滆繍琛屼笂涓嬫枃锛氱 15 绔犳柊澧炴暣鍚堝眰锛岀粺涓€鍒锋柊绗?7銆?銆?3銆?4 绔犵殑鍔ㄦ€佺姸鎬併€?

def update_context(context: dict, messages: list) -> dict:  # 鍒锋柊璁板繂銆丮CP 鍜岄槦鍙嬭繍琛屼笂涓嬫枃锛涙渶鏃╋細15.3039 鈭?    return {  # 姣忚疆閲嶆柊鏋勯€犲揩鐓э紝涓嶈宸茬粡鏂紑鐨勬湇鍔℃垨缁撴潫鐨勯槦鍙嬫畫鐣欏湪绯荤粺鎻愮ず璇嶄腑銆?        "memory_catalog": MEMORY_RUNTIME.read_memory_index(),  # 鐩綍鍙彁渚涢暱鏈熻蹇嗘瑙堬紝鎺у埗甯搁┗鎻愮ず璇嶄綋绉€?        "memories": MEMORY_RUNTIME.load_memories(messages),  # 鏍规嵁鏈€鏂板璇濋€夋嫨鐩稿叧璁板繂锛岃€屼笉鏄妸鍏ㄩ儴璁板繂鏃犲樊鍒敞鍏ャ€?        "connected_mcp": list(mcp_clients.keys()),  # MCP 鏄繍琛屾椂杩炴帴鐘舵€侊紝鍙兘鍦ㄤ笂涓€杞伐鍏疯皟鐢ㄥ悗鍙戠敓鍙樺寲銆?        "active_teammates": list(active_teammates.keys()),  # 鍥㈤槦鎴愬憳鏉ヨ嚜绾跨▼娉ㄥ唽琛紝鐢ㄤ簬璁?Lead 鎰熺煡褰撳墠鍗忎綔璧勬簮銆?    }


def remember_after_turn(messages: list) -> None:  # 姣忚疆缁撴潫鍚庢彁鍙栧苟鏁寸悊闀挎湡璁板繂锛涙渶鏃╋細15.3048  鈭?    if MEMORY_RUNTIME.extract_memories(messages):  # 鍙湁鏈疆纭疄鎻愬彇鍑烘柊璁板繂锛屾墠鏈夊繀瑕佽繘琛屾洿鏄傝吹鐨勬暣鐞嗐€?        MEMORY_RUNTIME.consolidate_memories()  # 鍚堝苟閲嶅鍜岃繃鏃惰褰曪紝闃叉闀挎湡杩愯鍚庤蹇嗙洰褰曟棤闄愯啫鑳€銆?

# -- Agent Loop --锝淎gent 寰幆锛氫互绗?3 绔犲惊鐜负楠ㄦ灦锛岀粺涓€缂栨帓绗?4鈥?4 绔犵殑閽╁瓙銆佸伐鍏枫€佽蹇嗐€佷换鍔°€佸悗鍙般€佸畾鏃躲€佸洟闃熷拰 MCP銆?
rounds_since_todo = 0  # 缁熻鏈洿鏂板緟鍔炵殑宸ュ叿杞暟锛岀敤娓╁拰鎻愰啋缁存寔闀夸换鍔＄殑缁撴瀯鍖栬繘搴︺€?agent_lock = threading.Lock()  # 鐢ㄦ埛杈撳叆涓庡紓姝ヤ簨浠跺叡鐢ㄥ悓涓€鍘嗗彶锛屽繀椤讳覆琛岃繘鍏ヤ富 Agent 寰幆銆?

def prepare_context(messages: list, active_request: str) -> list:  # 鎸夊眰绾у帇缂╁嵆灏嗗彂閫佺粰妯″瀷鐨勪笂涓嬫枃锛涙渶鏃╋細15.3059 鈭?    # Every LLM turn enters through the same context budget pipeline.锝滀腑鏂囷細姣忚疆妯″瀷璋冪敤閮界粡杩囧悓涓€濂椾笂涓嬫枃棰勭畻绠＄嚎銆?    messages[:] = tool_result_budget(messages)  # 绗竴灞傚彧澶勭悊鏈€鏂颁竴鎵瑰紓甯稿ぇ鐨勭粨鏋滐紝淇濊瘉涓嬩竴娆¤姹傞鍏堣兘澶熷彂鍑恒€?    messages[:] = snip_compact(messages)  # 绗簩灞傛寜娑堟伅鏁伴噺褰掓。涓锛屼繚鐣欎换鍔¤捣鐐瑰拰杩戞湡宸ヤ綔鐜板満銆?    if estimate_size(messages) > CONTEXT_LIMIT:  # 瀛楃棰勭畻浠嶈秴闄愭椂锛屾墠寮€濮嬫崯澶辨洿缁嗙矑搴︾殑宸ュ叿璇佹嵁銆?        target = int(CONTEXT_LIMIT * 0.8)  # 鍘嬪埌鍏垚鑰岄潪鍒氬ソ璐寸嚎锛屼负绯荤粺鎻愮ず璇嶅拰涓嬩竴杞粨鏋滈鐣欑┖闂淬€?        messages[:] = micro_compact(messages, target)  # 浼樺厛鎶婃ā鍨嬪凡娑堣垂鐨勬棫缁撴灉鏇挎崲涓虹鐩樺紩鐢ㄣ€?        if estimate_size(messages) > CONTEXT_LIMIT:  # 澶ч噺杩戞湡缁撴灉浠嶅彲鑳戒娇绗竴娆″井鍘嬬缉涓嶈冻銆?            messages[:] = fit_tool_results(messages, target)  # 鍐嶆寜浣撶Н浠庡ぇ鍒板皬鐢熸垚鏈夐檺棰勮銆?    if estimate_size(messages) > CONTEXT_LIMIT:  # 鍙湁缁撴瀯鍖栬鍓兘鏃犳硶瑙ｅ喅鏃舵墠浣跨敤妯″瀷鎽樿銆?        messages[:] = compact_history(messages, active_request)  # 鏈€缁堟湁鎹熷帇缂╀粛鍗曠嫭淇濈暀鏉冨▉鐢ㄦ埛璇锋眰銆?    return messages  # 杩斿洖鍚屼竴娑堟伅鍒楄〃锛岃皟鐢ㄦ柟鍜屽紓姝ヤ簨浠跺惊鐜户缁叡浜竴鑷村巻鍙层€?

def build_user_content(results: list[dict]) -> list[dict]:  # 鍚堝苟鍚屾宸ュ叿缁撴灉鍜屽悗鍙板畬鎴愰€氱煡锛涙渶鏃╋細15.3073 鈭?    # Tool results and completed background notifications are both returned to锝滀腑鏂囷細宸ュ叿缁撴灉鍜屽凡瀹屾垚鐨勫悗鍙伴€氱煡閮戒細浣滀负鐢ㄦ埛渚у唴瀹癸紝
    # the model as user-side content, matching the tool_result feedback loop.锝滀腑鏂囷細杩斿洖缁欐ā鍨嬶紝浠ョ鍚?tool_result 鍙嶉寰幆銆?    content = list(results)  # 澶嶅埗鍚屾缁撴灉鍒楄〃锛岄伩鍏嶉檮鍔犻€氱煡鏃朵慨鏀硅皟鐢ㄦ柟姝ｅ湪閬嶅巻鐨勬暟鎹€?    for note in collect_background_results():  # 鍘熷瓙鍙栬蛋姝ゅ墠宸插畬鎴愪絾灏氭湭鎶曢€掔殑鍚庡彴缁撴灉銆?        content.append({"type": "text", "text": note})  # 鍚庡彴閫氱煡涓嶆槸褰撳墠鍝嶅簲涓殑 tool_use 缁撴灉锛屽洜姝や綔涓烘櫘閫氭枃鏈潡杩藉姞銆?    return content  # 鍚屾缁撴灉涓庡紓姝ラ€氱煡鍦ㄥ悓涓€涓敤鎴锋秷鎭腑鍥炲埌妯″瀷銆?

def inject_background_notifications(messages: list):  # 灏嗗悗鍙板畬鎴愰€氱煡娉ㄥ叆娑堟伅鍘嗗彶锛涙渶鏃╋細15.3082 鈭?    notes = collect_background_results()  # 鍦ㄦ病鏈夊悓姝ュ伐鍏风粨鏋滅殑寮傛鍞ら啋鍦烘櫙涓崟鐙敹鍙栭€氱煡銆?    if notes:  # 娌℃湁鏂伴€氱煡鏃朵笉杩藉姞绌虹敤鎴锋秷鎭紝閬垮厤姹℃煋瀵硅瘽瑙掕壊浜ゆ浛銆?        messages.append({"role": "user", "content": [
            {"type": "text", "text": note} for note in notes]})  # 姣忎釜鍚庡彴浠诲姟淇濇寔鐙珛鏂囨湰鍧楋紝渚夸簬妯″瀷鍖哄垎浜嬩欢銆?

def call_llm(messages: list, context: dict, tools: list,  # 缁勮鎻愮ず璇嶅苟閫氳繃鎭㈠鏈哄埗璋冪敤妯″瀷锛涙渶鏃╋細15.3089  鈭?             state: RecoveryState, max_tokens: int):
    system = assemble_system_prompt(context)  # 鍦ㄨ皟鐢ㄥ墠鎵嶇粍瑁?Prompt锛岀‘淇濊蹇嗐€佹妧鑳姐€丮CP 鍜岄槦鍙嬬姸鎬侀兘鏄渶鏂板揩鐓с€?    return with_retry(  # 閲嶈瘯鍙寘鍥存ā鍨嬭姹傦紝涓嶉噸澶嶆墽琛屼换浣曞伐鍏峰壇浣滅敤銆?        lambda: client.messages.create(
            model=state.current_model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens),  # 杈撳嚭棰勭畻鐢卞綋鍓嶈疆娆＄殑鎴柇鎭㈠鐘舵€佸喅瀹氥€?        state)  # RecoveryState 鍦ㄥ娆″皾璇曢棿淇濈暀杩囪浇娆℃暟鍜屽綋鍓嶆ā鍨嬨€?

def agent_loop(messages: list, context: dict, active_request: str):  # 缁熶竴璋冨害妯″瀷銆佸伐鍏枫€佸畾鏃朵换鍔″拰涓婁笅鏂囷紱鏈€鏃╋細03.174 鈭?    global rounds_since_todo
    tools, handlers = assemble_tool_pool()  # 杩涘叆寰幆鍏堝缓绔嬪彲鐢ㄦ睜锛屽悗缁瘡杞繕浼氬埛鏂颁互绾冲叆鏂拌繛鎺ョ殑 MCP 宸ュ叿銆?    state = RecoveryState()  # 鎭㈠鐘舵€佸彧灞炰簬鏈 Agent 杩愯锛屾柊鐨勭敤鎴疯疆娆′粠棣栭€夋ā鍨嬪拰榛樿棰勭畻閲嶆柊寮€濮嬨€?    max_tokens = DEFAULT_MAX_TOKENS  # 姝ｅ父璋冪敤浣跨敤鍩虹棰勭畻锛屽彧鏈夊疄闄呮埅鏂悗鎵嶄复鏃舵墿瀹广€?
    unacknowledged_cron_jobs: list[CronJob] = []  # 淇濆瓨宸茬粡鍑洪槦銆佷絾妯″瀷灏氭湭鎴愬姛鎺ュ彈 Prompt 鐨勫畾鏃朵换鍔°€?    while True:  # 涓€娆″惊鐜搴斺€滄ā鍨嬪搷搴斺€旀墽琛屽伐鍏封€斿弽棣堢粨鏋溾€濓紝鏃犲伐鍏疯皟鐢ㄦ椂缁撴潫鏈疆 Agent銆?        # One cycle: inject scheduled/background work, prepare context, call锝滀腑鏂囷細鍗曟寰幆渚濇娉ㄥ叆瀹氭椂/鍚庡彴宸ヤ綔銆佸噯澶囦笂涓嬫枃銆佽皟鐢ㄦā鍨嬶紝
        # the model, execute tool_use blocks, append tool_results, repeat.锝滀腑鏂囷細鎵ц tool_use銆佽拷鍔?tool_result锛岀劧鍚庨噸澶嶃€?        fired = consume_cron_queue()  # 鍘熷瓙鍙栧嚭褰撳墠鍒版湡浠诲姟锛涙鏃跺皻涓嶈兘鍒犻櫎涓€娆℃€ф寔涔呰褰曘€?        unacknowledged_cron_jobs.extend(fired)  # 璇锋眰澶辫触鍓嶅缁堜繚鐣欏紩鐢紝浠ヤ究鎭㈠鍒伴槦鍒椼€?        for job in fired:  # 姣忎釜 Cron 閮借浆鎹负鏄庣‘鐨勭敤鎴蜂晶璇锋眰锛屽鐢ㄦ櫘閫?Agent 鎺ㄧ悊璺緞銆?            messages.append ({"role": "user",
                             "content": f"[瀹氭椂浠诲姟] {job.prompt}"})
            print(f"  \033[35m[cron inject] {job.prompt[:60]}\033[0m")
        if fired:  # 鍚屾椂鏇存柊 active_request锛岀‘淇濋殢鍚庡彂鐢熶笂涓嬫枃鍘嬬缉鏃跺畾鏃剁洰鏍囦笉浼氬彧瀛樺湪浜庤鎽樿鐨勫巻鍙蹭腑銆?            scheduled_requests = "\n".join(
                f"鎵ц瀹氭椂浠诲姟锛歿job.prompt}" for job in fired)
            active_request = f"{active_request}\n{scheduled_requests}".strip()

        inject_background_notifications(messages)  # 鍦ㄨ皟鐢ㄦā鍨嬪墠娉ㄥ叆宸插畬鎴愬悗鍙扮粨鏋滐紝浣垮叾涓?Cron 璇锋眰鍦ㄥ悓涓€杞瑙傚療銆?
        if rounds_since_todo >= 3:  # 杩炵画澶氫釜宸ュ叿鎿嶄綔鏈淮鎶ゅ緟鍔炴椂锛岃繍琛屾椂鎻愪緵鎻愰啋鑰屼笉鏄己琛屼慨鏀规ā鍨嬬姸鎬併€?            messages.append({"role": "user",
                             "content": "<reminder>璇锋洿鏂板緟鍔炰簨椤广€?/reminder>"})
            rounds_since_todo = 0  # 鎻愰啋鏈韩瑙嗕负涓€娆￠噸缃紝閬垮厤姣忚疆閲嶅娉ㄥ叆鐩稿悓娑堟伅銆?
        prepare_context(messages, active_request)  # 鎵€鏈夋潵婧愮殑娑堟伅姹囧悎鍚庣粺涓€鎵ц棰勭畻鎺у埗锛岄伩鍏嶆煇鏉″紓姝ヨ矾寰勭粫杩囧帇缂┿€?        context = update_context(context, messages)  # 鍘嬬缉鍚庣殑杩戞湡娑堟伅鍐冲畾璁板繂鍙洖锛屽洜姝や笂涓嬫枃鍒锋柊蹇呴』鍙戠敓鍦ㄥ帇缂╀箣鍚庛€?        tools, handlers = assemble_tool_pool()  # MCP 鍙兘鐢变笂涓€杞?connect_mcp 鍔ㄦ€佹帴鍏ワ紝姣忔璇锋眰鍓嶉噸鏂版瀯寤哄伐鍏锋睜銆?
        try:  # 妯″瀷璋冪敤澶辫触鏃朵笉鑳界‘璁ゅ凡鍙栧嚭鐨?Cron 浠诲姟銆?            response = call_llm(messages, context, tools, state, max_tokens)
        except Exception as e:  # with_retry 宸插鐞嗗彲閲嶈瘯閿欒锛屾澶勯潰瀵圭殑鏄渶缁堝け璐ユ垨涓嶅彲閲嶈瘯閿欒銆?            if is_prompt_too_long_error(e) and not state.has_attempted_reactive_compact:  # 瓒呴檺鍏佽涓€娆′笓鐢ㄧ揣鎬ユ仮澶嶃€?                messages[:] = reactive_compact(messages, active_request)
                state.has_attempted_reactive_compact = True  # 闃叉鎽樿浠嶈秴闄愭椂鏃犻檺閲嶅鏈夋崯瑁佸壀銆?                continue  # 淇濈暀鏈‘璁?Cron 鍒楄〃锛屽帇缂╁悗閲嶆柊灏濊瘯鍚屼竴璇锋眰銆?            restore_cron_jobs(unacknowledged_cron_jobs)  # 鏈€缁堝け璐ユ椂鎶婃湭鎺ュ彈鐨勫畾鏃朵换鍔￠噸鏂版斁鍥為槦鍒椼€?            messages.append({"role": "assistant", "content": [
                {"type": "text", "text": f"[閿欒] {type(e).__name__}锛歿e}"}]})  # 灏嗗け璐ヨ褰曡繘鍘嗗彶锛屼究浜庣晫闈㈠拰鍚庣画璇婃柇璇诲彇銆?            release_completed_assignment("agent")  # 浠呴噴鏀惧凡缁忓畬鎴愮殑 Lead 浠诲姟锛屼笉璇€€鍥炰粛鍦ㄨ繘琛岀殑宸ヤ綔銆?            return  # 缁撴潫褰撳墠杞锛屾妸鎺у埗鏉冧氦鍥?CLI 鎴栧紓姝ヤ簨浠跺惊鐜€?
        acknowledge_cron_jobs(unacknowledged_cron_jobs)  # 鍙湁妯″瀷鎴愬姛鎺ユ敹璇锋眰鍚庯紝鎵嶅垹闄や竴娆℃€?Cron 璁板綍銆?        unacknowledged_cron_jobs.clear()  # 娓呯┖浜嬪姟闆嗗悎锛岄槻姝㈠悗缁伐鍏烽樁娈甸敊璇噸澶嶆仮澶嶅凡纭浠诲姟銆?
        if response.stop_reason == "max_tokens":  # 鎴柇鍝嶅簲鍙兘鍖呭惈鏈畬鎴愭枃鏈垨宸ュ叿璋冪敤锛屼笉鑳藉綋浣滄甯哥粓姝€?            if not state.has_escalated:  # 绗竴灞傛仮澶嶄笉淇濆瓨鎴柇鍐呭锛岀洿鎺ョ敤鏇村ぇ棰勭畻閲嶈瘯鍚屼竴涓婁笅鏂囥€?                max_tokens = ESCALATED_MAX_TOKENS
                state.has_escalated = True  # 鏍囪宸叉墿瀹癸紝涓嬩竴娆′粛鎴柇鏃舵敼璧扮画鍐欒€岄潪鍐嶆鎵╁ぇ銆?                print(f"  \033[33m[max_tokens] 浣跨敤 {max_tokens} 涓?token 閲嶈瘯\033[0m")
                continue
            messages.append({"role": "assistant", "content": response.content})  # 鎵╁鍚庝粛鎴柇鏃朵繚鐣欏凡鐢熸垚閮ㄥ垎锛岄伩鍏嶆ā鍨嬩粠澶撮噸鍋氥€?            if state.recovery_count < MAX_RECOVERY_RETRIES:  # 缁啓娆℃暟鏈変笂闄愶紝闃叉妯″瀷鍙嶅杈撳嚭鏃犳硶闂悎鐨勯暱鍝嶅簲銆?                messages.append({"role": "user", "content": CONTINUATION_PROMPT})  # 鐢ㄤ腑鏂?Prompt 瑕佹眰浠庢柇鐐圭户缁笖涓嶉噸澶嶃€?                state.recovery_count += 1
                continue
            release_completed_assignment("agent")  # 鎭㈠鑰楀敖鍚庡畨鍏ㄧ粨鏉熻疆娆★紝涓嶆妸鏈畬鎴愪换鍔″己鍒舵爣涓哄畬鎴愩€?            return

        max_tokens = DEFAULT_MAX_TOKENS  # 鎴愬姛鑾峰緱瀹屾暣鍝嶅簲鍚庢仮澶嶅熀纭€棰勭畻锛屾墿瀹瑰彧鏈嶅姟浜庡彂鐢熸埅鏂殑闃舵銆?        state.has_escalated = False  # 鍏佽鏈潵鐙珛闃舵鍐嶆浣跨敤涓€娆℃墿瀹规満浼氥€?        messages.append({"role": "assistant", "content": response.content})  # 宸ュ叿缁撴灉蹇呴』寮曠敤宸茬粡杩涘叆鍘嗗彶鐨?assistant/tool_use銆?        if not has_tool_use(response.content):  # 娌℃湁瀹為檯宸ュ叿璋冪敤琛ㄧず妯″瀷宸插舰鎴愭湰杞渶缁堢瓟澶嶃€?            trigger_hooks("Stop", messages)  # 鍋滄閽╁瓙缁熶竴璁板綍缁熻淇℃伅锛屼絾涓嶆敼鍙樻渶缁堟枃鏈€?            remember_after_turn(messages)  # 鍙湪瀹屾暣鑷劧缁撴潫鏃舵彁鍙栭暱鏈熻蹇嗭紝閬垮厤淇濆瓨涓棿宸ュ叿璁″垝銆?            release_completed_assignment("agent")  # Lead 浠诲姟鑻ュ凡瀹屾垚锛屽湪鏄庣‘杞杈圭晫閲婃斁 cwd 绉熺害銆?            return

        results = []  # 鏀堕泦鏈鍝嶅簲涓叏閮ㄥ伐鍏疯皟鐢ㄧ殑閰嶅缁撴灉锛屾渶鍚庣粺涓€杩藉姞涓虹敤鎴锋秷鎭€?        compact_requested = False  # compact 鏄帶鍒朵俊鍙凤紝闇€鍏堥棴鍚堝綋鍓嶅伐鍏疯疆娆★紝鍐嶆浛鎹㈠巻鍙层€?        for block in response.content:  # 鍝嶅簲鍙兘娣峰悎鏂囨湰涓庡涓伐鍏峰潡锛岄€愬潡淇濇寔鍘熷椤哄簭澶勭悊銆?            if block.type != "tool_use":  # 鏂囨湰宸茬粡闅?assistant 鍝嶅簲淇濆瓨锛屼笉鍙備笌宸ュ叿鍒嗗彂銆?                continue
            print(f"\033[36m> {block.name}\033[0m")

            if block.name == "compact":  # 涓诲姩鍘嬬缉涓嶈蛋鏅€?handler锛屽洜涓哄畠闇€瑕佸湪褰撳墠 tool_result 鍏ュ巻鍙插悗鎵ц銆?                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "[宸茶姹傚帇缂╋紱褰撳墠宸插畬鎴愯疆娆″皢琚€荤粨銆俔",
                })
                compact_requested = True  # 寤惰繜鍒版墍鏈夊苟鍒楀伐鍏峰潡澶勭悊瀹屽悗缁熶竴鍘嬬缉銆?                continue  # compact 鏈韩娌℃湁澶栭儴鍓綔鐢紝鏃犻渶瑙﹀彂鏉冮檺鍜屽悗缃挬瀛愩€?
            blocked = trigger_hooks("PreToolUse", block)  # 鏉冮檺銆丮CP 绛栫暐鍜屾棩蹇楀湪鍒嗗彂鍓嶇粺涓€鎵ц銆?            if blocked:  # 閽╁瓙杩斿洖鍐呭琛ㄧず璋冪敤琚嫆缁濇垨闇€瑕佸仠姝紝涓嶈兘缁х画鎵ц handler銆?                results.append({"type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(blocked)})
                continue  # 鎷掔粷涔熷繀椤讳綔涓哄悎娉?tool_result 鍥炰紶锛屾ā鍨嬫墠鑳借皟鏁存柟妗堛€?
            if should_run_background(block.name, block.input):  # 鍙湁鏄惧紡瑕佹眰鍚庡彴杩愯鐨?Bash 鎵嶈蛋寮傛鍒嗘敮銆?                try:  # 鍚姩鎴愬姛鍙繑鍥炲崰浣嶇粨鏋滐紝鐪熷疄缁撴灉鐢变簨浠跺惊鐜◢鍚庢姇閫掋€?                    bg_id = start_background_task(block, handlers)
                    output = (f"[鍚庡彴浠诲姟 {bg_id} 宸插惎鍔╙ "
                              "缁撴灉绋嶅悗灏嗛€氳繃 task_notification 鍒拌揪銆?)
                except Exception as exc:  # 鍚姩澶辫触浠嶉渶闂悎褰撳墠 tool_use锛屼笉鑳借鍗忚鎮┖銆?                    output = (f"閿欒锛氬悗鍙颁换鍔″惎鍔ㄥけ璐ワ細"
                              f"{type(exc).__name__}锛歿exc}")
                results.append({"type": "tool_result",
                                "tool_use_id": block.id,
                                "content": output})
                continue  # 鍚庡彴 worker 鑷繁鎵ц PostToolUse锛涗富绾跨▼涓嶈兘鎻愬墠瑙﹀彂銆?
            handler = handlers.get(block.name)  # 鍔ㄦ€佹睜鍚屾椂鍖呭惈鍐呯疆鍜?MCP 闂寘锛屽垎鍙戦€昏緫鏃犻渶鍖哄垎鏉ユ簮銆?            output = call_tool_handler(handler, block.input, block.name)  # 缁熶竴澶勭悊鏈煡宸ュ叿銆佸弬鏁颁笉鍖归厤鍜屾墽琛屽紓甯搞€?            trigger_hooks("PostToolUse", block, output)  # 澶ц緭鍑鸿惤鐩樼瓑琛屼负鍙湪鍚屾鎵ц瀹屾垚鍚庡彂鐢熴€?            print(str(output)[:300])  # 缁堢鍙睍绀虹煭棰勮锛屽畬鏁村唴瀹逛粛杩涘叆缁撴灉鎴栨寔涔呭寲鏂囦欢銆?
            if block.name == "todo_write":  # 妯″瀷涓诲姩缁存姢寰呭姙鍚庨噸鏂板紑濮嬫彁閱掕鏁般€?                rounds_since_todo = 0
            else:
                rounds_since_todo += 1  # 鎸夊伐鍏疯皟鐢ㄨ€岄潪妯″瀷杞璁℃暟锛屾洿鑳藉弽鏄犻暱浠诲姟瀹為檯杩涘睍銆?
            results.append({"type": "tool_result",
                            "tool_use_id": block.id, "content": output})

        messages.append({"role": "user", "content": build_user_content(results)})  # 闂悎鎵€鏈?tool_use锛屽苟椤哄甫鎶曢€掑凡瀹屾垚鍚庡彴閫氱煡銆?        if compact_requested:  # 蹇呴』鍦?tool_result 宸茶繘鍏ュ巻鍙插悗鍘嬬缉锛屽惁鍒欎細鐣欎笅鏈厤瀵硅皟鐢ㄣ€?            messages[:] = compact_history(messages, active_request)  # 鐢ㄥ畨鍏ㄦ憳瑕佹浛鎹㈠巻鍙诧紝涓嬩竴杞粠鍚屼竴 while 寰幆缁х画銆?

def print_turn_assistants(messages: list, turn_start: int):  # 杈撳嚭鏈疆鏂板鐨勬ā鍨嬫枃鏈紱鏈€鏃╋細15.3227  鈭?    for msg in messages[turn_start:]:  # 鍙煡鐪嬫湰娆″叆鍙ｄ箣鍚庢柊澧炵殑娑堟伅锛岄伩鍏嶉噸澶嶆墦鍗板巻鍙茬瓟澶嶃€?        if msg.get("role") != "assistant":  # 鐢ㄦ埛宸ュ叿缁撴灉鍜屼簨浠舵敞鍏ヤ笉搴斾綔涓烘渶缁堣緭鍑虹洿鎺ュ睍绀恒€?            continue
        for block in msg.get("content", []):  # 涓€杞彲鑳藉洜宸ュ叿寰幆浜х敓澶氭潯 assistant 娑堟伅銆?            if block_type(block) == "text":  # 鍙墦鍗拌嚜鐒惰瑷€鍧楋紝tool_use 宸插湪鎵ц鏃跺崟鐙樉绀恒€?                terminal_print(block["text"] if isinstance(block, dict) else block.text)


def async_event_loop(history: list, context: dict, session_state: dict):  # 鑷姩澶勭悊瀹氭椂浠诲姟銆佸悗鍙扮粨鏋滃拰鍥㈤槦娑堟伅锛涙渶鏃╋細15.3236
    while True:  # 鍚庡彴浜嬩欢娉佃娌℃湁鐢ㄦ埛鏁插洖杞︽椂锛岀郴缁熶簨浠朵篃鑳戒富鍔ㄥ敜閱?Lead銆?        time.sleep(1)  # 涓€绉掕疆璇㈡帶鍒跺搷搴斿紑閿€锛汣ron 鑷韩浠嶆寜鍒嗛挓鍘婚噸锛屼笉鍙楄疆璇㈤鐜囧奖鍝嶃€?        with agent_lock:  # 涓庡墠鍙拌緭鍏ュ叡浜巻鍙插拰妯″瀷瀹㈡埛绔紝鏁翠釜鑷姩杞蹇呴』涓茶銆?            with cron_lock:  # 杩欓噷鍙揩鐓ч槦鍒楀垽鏂槸鍚﹂渶瑕佸敜閱掞紝鐪熸鍙栧嚭鐢?agent_loop 瀹屾垚銆?                fired = list(cron_queue)
            inbox = consume_lead_inbox(route_protocol=True)  # 鍗忚鍝嶅簲鍏堟洿鏂扮姸鎬佹満锛屽啀鎶婂彲瑙佷簨浠朵氦缁?Lead銆?            if not fired and not inbox and not has_pending_background():  # 娌℃湁浠讳綍浜嬩欢鏃朵笉璋冪敤妯″瀷銆?                continue
            turn_start = len(history)  # 璁板綍鑷姩杞璧风偣锛岀粨鏉熷悗鍙墦鍗版柊鐢熸垚鐨勬枃鏈€?            scheduled_requests = []  # active_request 闇€瑕佺嫭绔嬩繚瀛?Cron 鐩爣锛屼互渚垮帇缂╂椂鎴愪负鏉冨▉璇锋眰銆?            for job in fired:
                scheduled_requests.append(f"鎵ц瀹氭椂浠诲姟锛歿job.prompt}")
                terminal_print(
                    f"  \033[35m[cron auto] {job.prompt[:60]}\033[0m")
            if inbox:  # 鍥㈤槦浜嬩欢浣滀负鐢ㄦ埛娑堟伅杩涘叆涓诲巻鍙诧紝璁?Lead 鑳藉熀浜庣粨鏋滅户缁崗璋冦€?                history.append({"role": "user",
                                "content": format_team_events(inbox)})
                terminal_print(
                    f"  \033[33m[team auto] {len(inbox)} events\033[0m")
            active_request = (  # Cron 浼樺厛鎴愪负鏈疆鏉冨▉鐩爣锛涘彧鏈夌函鍥㈤槦/鍚庡彴浜嬩欢鏃舵墠娌跨敤鏈€杩戠敤鎴疯姹傘€?                "\n".join(scheduled_requests)
                if scheduled_requests
                else session_state["active_user_request"]
            )
            agent_loop(history, context, active_request)  # 鎵€鏈夊紓姝ユ潵婧愭渶缁堝鐢ㄥ悓涓€涓畨鍏ㄣ€佸帇缂╁拰宸ュ叿鎵ц绠＄嚎銆?            context.update(update_context(context, history))  # 鍘熷湴鏇存柊涓荤嚎绋嬪叡浜瓧鍏革紝閬垮厤鍚庡彴绾跨▼鏇挎崲瀵硅薄鍚庡墠鍙版寔鏈夋棫寮曠敤銆?            print_turn_assistants(history, turn_start)  # 浣跨敤绾跨▼瀹夊叏缁堢杈撳嚭锛屽苟鎭㈠鐢ㄦ埛灏氭湭鎻愪氦鐨勮緭鍏ヨ銆?

if __name__ == "__main__":
    CLI_ACTIVE = True  # 浠呯洿鎺ヨ繍琛岃剼鏈椂鍚敤 Readline 閲嶇粯锛涗綔涓烘ā鍧楀鍏ヤ笉浼氬惎鍔ㄤ氦浜掑壇浣滅敤銆?    start_runtime_services()  # 鍦ㄦ帴鏀惰緭鍏ュ墠鎭㈠鎸佷箙 Cron 骞跺惎鍔ㄥ敮涓€璋冨害绾跨▼銆?    print("绗?15 绔狅細闆嗘垚杩愯妗嗘灦")
    print("璇疯緭鍏ラ棶棰樺苟鎸?Enter 鍙戦€侊紱杈撳叆 q 鍙€€鍑恒€俓n")
    history = []  # 鍓嶅彴鐢ㄦ埛鍜屽悗鍙颁簨浠跺叡浜繖浠戒富 Agent 娑堟伅鍘嗗彶銆?    context = update_context({}, [])  # 鍚姩鏃跺缓绔嬮浠借蹇嗐€丮CP 鍜屽洟闃熺姸鎬佸揩鐓с€?    session_state = {"active_user_request": "锛堝綋鍓嶆病鏈夌敤鎴疯姹傦級"}  # 寮傛浜嬩欢闇€瑕佸紩鐢ㄦ渶杩戣姹傦紝浣嗕笉鑳戒粠鍘嬬缉鍘嗗彶涓寽娴嬨€?    threading.Thread(target=async_event_loop,
                     args=(history, context, session_state), daemon=True).start()  # 浜嬩欢娉典綔涓哄畧鎶ょ嚎绋嬭繍琛岋紝涓嶉樆姝㈢敤鎴烽€€鍑虹▼搴忋€?    while True:  # 鍓嶅彴寰幆鍙礋璐ｆ敹闆嗙敤鎴疯緭鍏ワ紝瀹為檯妯″瀷宸ヤ綔鍏ㄩ儴濮旀墭缁?agent_loop銆?        try:
            query = CONSOLE.ask()  # 閫氳繃 ConsoleBroker 涓庡悗鍙版潈闄愯闂覆琛屽叡浜爣鍑嗚緭鍏ャ€?        except (EOFError, KeyboardInterrupt):  # 鏂囦欢缁撴潫鍜?Ctrl+C 閮借涓烘甯搁€€鍑哄叆鍙ｃ€?            break
        if query.strip().lower() in ("q", "exit", ""):  # 绌鸿緭鍏ヤ笉鍒涘缓鏃犳剰涔夋ā鍨嬭疆娆°€?            break
        with agent_lock:  # 闃叉寮傛 Cron 鎴栧洟闃熶簨浠跺湪鍚屼竴鏃堕棿淇敼鍘嗗彶骞惰皟鐢ㄦā鍨嬨€?            trigger_hooks("UserPromptSubmit", query)  # 鍦ㄦ秷鎭叆鍘嗗彶鍓嶈褰曞綋鍓嶅伐浣滅洰褰曠瓑璇锋眰绾т笂涓嬫枃銆?            turn_start = len(history)  # 鐢ㄤ簬鏈€缁堝彧杈撳嚭鏈疆浜х敓鐨勫姪鎵嬫枃鏈€?            session_state["active_user_request"] = query  # 鐙珛淇濆瓨鏉冨▉璇锋眰锛屼緵鍚庡彴鍞ら啋鍜屼笂涓嬫枃鍘嬬缉浣跨敤銆?            history.append({"role": "user", "content": query})  # 鐢ㄦ埛鍘熸枃涓嶅仛閲嶅啓锛岀洿鎺ヨ繘鍏ユā鍨嬪巻鍙层€?            agent_loop(history, context, query)  # 澶嶇敤涓庡紓姝ヤ簨浠跺畬鍏ㄧ浉鍚岀殑缁熶竴缂栨帓寰幆銆?            context = update_context(context, history)  # 鏈疆鍙兘杩炴帴 MCP銆佹敼鍙橀槦鍙嬫垨鍐欏叆璁板繂锛岀粨鏉熷悗鍒锋柊蹇収銆?            print_turn_assistants(history, turn_start)  # 杈撳嚭鏈疆鍏ㄩ儴鏈€缁堟枃鏈紝涓嶉噸澶嶆樉绀烘棫鍘嗗彶銆?        print()

