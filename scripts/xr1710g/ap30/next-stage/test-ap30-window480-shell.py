"""Run the frozen AP30 shell against the exact new 480s recovery request."""
from pathlib import Path
w=Path('/mnt/d/ChatGPT/XR1710G')
s=(w/'environment/test-ap30-npu-recovery-shell.py').read_text()
s=s.replace('development/ap30/npu-gates/ap1','development/ap30/npu-window480/recovery')
s=s.replace('exact240','exact480').replace('[ "$2" = 240 ]','[ "$2" = 480 ]')
exec(compile(s,'AP30-window480-shipped-shell','exec'),{'__name__':'__main__'})
