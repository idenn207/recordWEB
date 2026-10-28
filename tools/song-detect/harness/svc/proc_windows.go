package main

import (
	"os/exec"
	"syscall"
)

// cap80 모드의 작업자는 BELOW_NORMAL_PRIORITY_CLASS(0x4000): limits.py/nas_ingest 와 같은 방식(사용자가 같은 PC 를 쓰므로 양보)
func lowPriority(c *exec.Cmd) { c.SysProcAttr = &syscall.SysProcAttr{CreationFlags: 0x4000} }
