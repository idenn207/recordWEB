// songd: song-detect 하네스의 얇은 작업 큐 HTTP 서비스(시제품). 상주 파이썬 작업자(harness/worker.py)를 풀로 두고 JSON 작업을 분배한다.
//   POST /jobs?wait=1  {"op":"replay","args":{...}}  -> 작업 접수(wait=1 이면 끝날 때까지 기다려 결과를 바로 응답)
//   GET  /jobs/{id}    -> {status: queued|running|done|error, result, queue_ms, run_ms}
//   POST /mode         {"mode":"cap80"|"unlimited"}  리소스 모드 전환(작업자 수와 우선순위, 진행 중 작업은 끝까지)
//   GET  /healthz
// 리소스 모드: cap80 = 논리 코어의 80% 작업자 + 낮은 우선순위(기본, limits.py 의 SONG_LIMIT_PCT 와 같은 취지) / unlimited = 전 코어 + 보통 우선순위.
// shortcut: 작업 저장은 메모리(재시작하면 사라짐), 인증 없음(127.0.0.1 만 listen), GPU 작업(분석기 컨테이너 8765)은 이 큐를 거치지 않는다 - 붙일 때는 gpu 세마포어 1.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"sync"
	"time"
)

type Job struct {
	ID      string          `json:"id"`
	Op      string          `json:"op"`
	Args    json.RawMessage `json:"args,omitempty"`
	Status  string          `json:"status"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   string          `json:"error,omitempty"`
	QueueMs float64         `json:"queue_ms"`
	RunMs   float64         `json:"run_ms"`
	enq     time.Time
	done    chan struct{}
}

type Server struct {
	mu     sync.Mutex
	jobs   map[string]*Job
	seq    int
	q      chan *Job
	mode   string
	quit   []chan struct{}
	py, wk string
	nDone  int
}

type req struct {
	ID   string          `json:"id"`
	Op   string          `json:"op"`
	Args json.RawMessage `json:"args,omitempty"`
}
type resp struct {
	ID     string          `json:"id"`
	Ok     bool            `json:"ok"`
	Result json.RawMessage `json:"result"`
	Error  string          `json:"error"`
	Ms     float64         `json:"ms"`
}

var override int // -n 으로 작업자 수 고정(측정용)

func workersFor(mode string) int {
	if override > 0 {
		return override
	}
	n := runtime.NumCPU()
	if mode == "cap80" {
		n = n * 80 / 100
	}
	if n < 1 {
		n = 1
	}
	return n
}

func (s *Server) worker(quit chan struct{}, lowPrio bool) {
	cmd := exec.Command(s.py, s.wk)
	if lowPrio {
		lowPriority(cmd)
	}
	in, _ := cmd.StdinPipe()
	out, _ := cmd.StdoutPipe()
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		log.Printf("작업자 시작 실패: %v", err)
		return
	}
	rd := bufio.NewReaderSize(out, 1<<20)
	defer func() { in.Close(); cmd.Wait() }()
	if _, err := rd.ReadBytes('\n'); err != nil { // {"ready":true}
		log.Printf("작업자 준비 실패: %v", err)
		return
	}
	for {
		select {
		case <-quit:
			return
		case j := <-s.q:
			s.mu.Lock()
			j.Status, j.QueueMs = "running", float64(time.Since(j.enq).Microseconds())/1000
			s.mu.Unlock()
			t := time.Now()
			b, _ := json.Marshal(req{j.ID, j.Op, j.Args})
			in.Write(append(b, '\n'))
			line, err := rd.ReadBytes('\n')
			var r resp
			if err == nil {
				err = json.Unmarshal(line, &r)
			}
			s.mu.Lock()
			j.RunMs = float64(time.Since(t).Microseconds()) / 1000
			switch {
			case err != nil:
				j.Status, j.Error = "error", err.Error()
			case !r.Ok:
				j.Status, j.Error = "error", r.Error
			default:
				j.Status, j.Result = "done", r.Result
			}
			s.nDone++
			s.mu.Unlock()
			close(j.done)
		}
	}
}

// setMode: 이전 작업자들에게 종료 신호(현재 작업은 끝까지 하고 나감)를 주고 새 모드의 작업자를 올린다.
func (s *Server) setMode(mode string) {
	s.mu.Lock()
	for _, q := range s.quit {
		close(q)
	}
	s.quit, s.mode = nil, mode
	n := workersFor(mode)
	for i := 0; i < n; i++ {
		q := make(chan struct{})
		s.quit = append(s.quit, q)
		go s.worker(q, mode == "cap80")
	}
	s.mu.Unlock()
}

func (s *Server) submit(op string, args json.RawMessage) *Job {
	s.mu.Lock()
	s.seq++
	j := &Job{ID: fmt.Sprintf("j%d", s.seq), Op: op, Args: args, Status: "queued", enq: time.Now(), done: make(chan struct{})}
	s.jobs[j.ID] = j
	s.mu.Unlock()
	s.q <- j
	return j
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

func main() {
	addr := flag.String("addr", "127.0.0.1:8790", "listen")
	mode := flag.String("mode", "cap80", "cap80|unlimited")
	py := flag.String("py", "python", "python 실행 파일")
	wk := flag.String("worker", "../worker.py", "worker.py 경로")
	flag.IntVar(&override, "n", 0, "작업자 수 고정(0 이면 모드가 정함)")
	flag.Parse()
	s := &Server{jobs: map[string]*Job{}, q: make(chan *Job, 4096), py: *py, wk: *wk}
	s.setMode(*mode)
	mux := http.NewServeMux()
	mux.HandleFunc("POST /jobs", func(w http.ResponseWriter, r *http.Request) {
		var in struct {
			Op   string          `json:"op"`
			Args json.RawMessage `json:"args"`
		}
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.Op == "" {
			writeJSON(w, 400, map[string]string{"error": "op 필요"})
			return
		}
		j := s.submit(in.Op, in.Args)
		if r.URL.Query().Get("wait") == "1" {
			<-j.done
			s.mu.Lock()
			defer s.mu.Unlock()
			writeJSON(w, 200, j)
			return
		}
		writeJSON(w, 202, map[string]string{"id": j.ID})
	})
	mux.HandleFunc("GET /jobs/{id}", func(w http.ResponseWriter, r *http.Request) {
		s.mu.Lock()
		defer s.mu.Unlock()
		j, ok := s.jobs[r.PathValue("id")]
		if !ok {
			writeJSON(w, 404, map[string]string{"error": "없는 작업"})
			return
		}
		writeJSON(w, 200, j)
	})
	mux.HandleFunc("POST /mode", func(w http.ResponseWriter, r *http.Request) {
		var in struct{ Mode string }
		if json.NewDecoder(r.Body).Decode(&in) != nil || (in.Mode != "cap80" && in.Mode != "unlimited") {
			writeJSON(w, 400, map[string]string{"error": "mode 는 cap80 또는 unlimited"})
			return
		}
		s.setMode(in.Mode)
		writeJSON(w, 200, map[string]any{"mode": in.Mode, "workers": workersFor(in.Mode)})
	})
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		s.mu.Lock()
		defer s.mu.Unlock()
		writeJSON(w, 200, map[string]any{"mode": s.mode, "workers": len(s.quit), "queued": len(s.q), "done": s.nDone, "cpus": runtime.NumCPU()})
	})
	log.Printf("songd %s mode=%s workers=%d", *addr, *mode, workersFor(*mode))
	log.Fatal(http.ListenAndServe(*addr, mux))
}
