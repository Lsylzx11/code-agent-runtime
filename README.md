# Code Agent Runtime

涓€涓潰鍚戜唬鐮佷粨搴撲换鍔＄殑銆佸彲娴嬭瘯鐨?Python Code Agent Runtime銆?
瀹冨皢鍗?Agent 宸ュ叿璋冪敤銆佸 Agent 浠诲姟 DAG銆侀暱鏈熻蹇嗐€丮CP 宸ュ叿鎺ュ叆銆丟it worktree 闅旂銆佸彧璇讳唬鐮佸鏌ヤ笌鏄惧紡鍚堝苟瀹℃壒缁勫悎涓轰竴涓彲鎭㈠鐨勬湰鍦拌繍琛屾椂銆?
## 鑳藉姏

- 宸ヤ綔鍖哄彈闄愮殑鏂囦欢璇诲彇銆佹悳绱€佺紪杈戜笌鍛戒护鎵ц
- 宸ュ叿鏉冮檺绛栫暐銆佸懡浠よ秴鏃朵笌缁撴瀯鍖栧伐鍏风粨鏋?- 澶氳疆 LLM Tool Calling Agent Loop
- 鏂囦欢鍨嬮暱鏈熻蹇嗕笌 MCP 鍔ㄦ€佸伐鍏锋敞鍐?- LLM 椹卞姩鐨?JSON Task DAG 瑙勫垝涓庝緷璧栬皟搴?- 鐙珛 SubAgent 涓婁笅鏂囧拰 checkpoint/resume
- 鍐欎换鍔＄殑 Git worktree / 鍒嗘敮闅旂
- 鍙 Review Agent銆乨iff 鎸囩汗鏍￠獙鍜屾樉寮忓鎵瑰悎骞?
## 瀹夎

```bash
python -m pip install -e .
```

閰嶇疆妯″瀷锛?
```bash
# PowerShell 绀轰緥
$env:ANTHROPIC_API_KEY = "..."
$env:MODEL_ID = "..."
```

涔熸敮鎸侀€氳繃 `ANTHROPIC_BASE_URL` 杩炴帴鍏煎缃戝叧銆?
## 鍗?Agent

```bash
code-agent "妫€鏌ュ苟淇娴嬭瘯澶辫触" --workspace /path/to/repository --allow-execute
```

## 澶?Agent Git 宸ヤ綔娴?
鐩爣浠撳簱蹇呴』鏄凡鏈夊垵濮嬫彁浜ょ殑 Git 浠撳簱锛?
```bash
code-agent "淇澶辫触娴嬭瘯锛岃繍琛岄獙璇侊紝骞跺鏌ヤ慨鏀? \
  --workspace /path/to/repository \
  --workflow \
  --workflow-id fix-issue-42 \
  --allow-execute
```

榛樿鍙湪闅旂 worktree 涓慨鏀广€傚彧鏈夊鏌?JSON 杩斿洖 `approved`銆乨iff 鎸囩汗娌℃湁鍙樺寲銆佷富宸ヤ綔鍖哄共鍑€锛屽苟涓旂敤鎴锋樉寮忎紶鍏?`--merge-reviewed` 鏃讹紝鎵嶄細鎻愪氦骞跺悎骞惰鍙樻洿锛?
```bash
code-agent "..." --workspace /path/to/repository --workflow \
  --workflow-id fix-issue-42 --allow-execute --merge-reviewed
```

## 娴嬭瘯

```bash
python -m unittest discover -s tests -v
```

## 闄愬埗

褰撳墠鍛戒护鎵ц浠嶄緷璧?`shell=True` 鍜岀瓥鐣ラ檺鍒讹紝骞堕潪瀹瑰櫒绾ф矙绠憋紱MCP 灞傜洰鍓嶆彁渚涚粺涓€娉ㄥ唽/璋冨害鎺ュ彛锛屽皻鏈唴缃敓浜х骇 stdio/HTTP transport銆?
[`15.py`](15.py) 鏄師濮嬭绋嬫暣鍚?Harness 鐨勪繚鐣欏弬鑰冨疄鐜帮紱褰撳墠鍙淮鎶よ繍琛屾椂浣嶄簬 [`code_agent/`](code_agent/)銆?
