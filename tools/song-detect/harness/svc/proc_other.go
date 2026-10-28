//go:build !windows

package main

import "os/exec"

// shortcut: 윈도우 외에는 우선순위를 안 낮춘다(nice 는 배포 환경이 정해지면)
func lowPriority(c *exec.Cmd) {}
