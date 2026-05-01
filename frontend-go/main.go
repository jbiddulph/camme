package main

import (
	"bytes"
	"crypto/tls"
	_ "embed" // required for //go:embed
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
)

//go:embed static/exhibitionist.png
var embeddedExhibitionistPNG []byte

type RoomResponse struct {
	Rooms []string `json:"rooms"`
}

type CreateRoomResponse struct {
	RoomName     string `json:"room_name"`
	HostToken    string `json:"host_token"`
	ViewerToken  string `json:"viewer_token"`
	LivekitURL   string `json:"livekit_url"`
	LivekitWsURL string `json:"livekit_ws_url"`
}

type RoomRow struct {
	Name     string
	WatchURL string
}

type PageData struct {
	BackendURL string
	APIPrefix  string
	Rooms      []RoomRow
	Error      string
}

type AuthPageData struct {
	BackendURL string
	APIPrefix  string
}

type viewerTokenPayload struct {
	RoomName     string `json:"room_name"`
	ViewerToken  string `json:"viewer_token"`
	LivekitWsURL string `json:"livekit_ws_url"`
}

type LivePageData struct {
	APIPrefix string
}

func envOrDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

// trimSurroundingQuotes removes one layer of matching " or ' wrappers.
// Common when .env files use API_PREFIX="/api/v1" and the loader keeps the quotes.
func trimSurroundingQuotes(s string) string {
	s = strings.TrimSpace(s)
	for len(s) >= 2 {
		first, last := s[0], s[len(s)-1]
		if (first == '"' && last == '"') || (first == '\'' && last == '\'') {
			s = strings.TrimSpace(s[1 : len(s)-1])
			continue
		}
		break
	}
	return s
}

func normalizeAPIPrefix(p string) string {
	p = trimSurroundingQuotes(strings.TrimSpace(p))
	p = strings.TrimSuffix(p, "/")
	if p == "" {
		return "/api/v1"
	}
	if !strings.HasPrefix(p, "/") {
		p = "/" + p
	}
	return p
}

func fetchRooms(backendURL, apiPrefix string) ([]string, error) {
	resp, err := http.Get(strings.TrimSuffix(backendURL, "/") + apiPrefix + "/rooms")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("rooms API returned %d", resp.StatusCode)
	}

	var payload RoomResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, err
	}

	return payload.Rooms, nil
}

func validateBackendURLForHeroku(backend string) {
	if os.Getenv("DYNO") == "" {
		return
	}
	b := strings.ToLower(backend)
	if strings.Contains(b, "localhost") || strings.Contains(b, "127.0.0.1") || strings.Contains(b, "::1") {
		log.Fatal(
			"Heroku: BACKEND_BASE_URL must be your FastAPI app URL (https://…herokuapp.com), not localhost. " +
				"Run: heroku config:set BACKEND_BASE_URL=https://<camme-api>.herokuapp.com -a camme-web",
		)
	}
	if !strings.HasPrefix(b, "https://") {
		log.Printf("warning: BACKEND_BASE_URL should use https:// on Heroku (got %q)", backend)
	}
}

func main() {
	backendURL := trimSurroundingQuotes(envOrDefault("BACKEND_BASE_URL", "http://localhost:8000"))
	validateBackendURLForHeroku(backendURL)
	apiPrefix := normalizeAPIPrefix(envOrDefault("API_PREFIX", "/api/v1"))
	port := envOrDefault("PORT", "8080")

	tmpl := template.Must(template.New("").Funcs(template.FuncMap{
		"jsString": func(s string) template.JS {
			b, err := json.Marshal(s)
			if err != nil {
				return template.JS(`""`)
			}
			return template.JS(b)
		},
	}).ParseGlob("templates/*.html"))
	mux := http.NewServeMux()

	mux.HandleFunc("/static/exhibitionist.png", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/png")
		w.Header().Set("Cache-Control", "public, max-age=86400")
		_, _ = w.Write(embeddedExhibitionistPNG)
	})
	mux.Handle("/static/", http.StripPrefix("/static/", http.FileServer(http.Dir("static"))))

	apiTarget, err := url.Parse(backendURL)
	if err != nil {
		log.Fatal(err)
	}
	if apiTarget.Scheme == "" || apiTarget.Host == "" {
		log.Fatalf("BACKEND_BASE_URL must include scheme and host (e.g. http://localhost:8000), got %q", backendURL)
	}
	// Only scheme+host: a path on BACKEND_BASE_URL (e.g. .../api/v1) would otherwise join twice with /api/v1/...
	proxyOrigin := &url.URL{Scheme: apiTarget.Scheme, Host: apiTarget.Host}
	// NewSingleHostReverseProxy does not rewrite the Host header; browsers send the web app's Host,
	// so Heroku would route the outbound request to the wrong app and close with EOF. Use Rewrite + SetURL.
	apiProxy := &httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.SetURL(proxyOrigin)
			// SetURL clears Host; ensure the API vhost is explicit (Heroku routes by Host).
			pr.Out.Host = proxyOrigin.Host
			pr.SetXForwarded()
		},
	}
	// Outbound HTTP/2 to some edge setups can yield EOF; HTTP/1.1 is reliable for server-side proxy hops.
	apiTransport := http.DefaultTransport.(*http.Transport).Clone()
	apiTransport.TLSNextProto = make(map[string]func(string, *tls.Conn) http.RoundTripper)
	apiProxy.Transport = apiTransport
	apiProxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		log.Printf("api proxy error: %v", err)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		_, _ = fmt.Fprintf(w, `{"detail":"cannot reach API backend at %s: %v"}`, proxyOrigin.String(), err)
	}

	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		roomNames, err := fetchRooms(backendURL, apiPrefix)
		rows := make([]RoomRow, 0, len(roomNames))
		for _, name := range roomNames {
			rows = append(rows, RoomRow{
				Name:     name,
				WatchURL: "/watch?room=" + url.QueryEscape(name),
			})
		}
		page := PageData{BackendURL: backendURL, APIPrefix: apiPrefix, Rooms: rows}
		if err != nil {
			page.Error = "Could not fetch rooms from API"
		}

		if err := tmpl.ExecuteTemplate(w, "index.html", page); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
	})

	mux.HandleFunc("/auth", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		page := AuthPageData{BackendURL: backendURL, APIPrefix: apiPrefix}
		if err := tmpl.ExecuteTemplate(w, "auth.html", page); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
	})

	mux.HandleFunc("/cam-test", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if err := tmpl.ExecuteTemplate(w, "cam-test.html", nil); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
	})

	mux.HandleFunc("/tips/inbox", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		http.Redirect(w, r, "/tips", http.StatusFound)
	})

	mux.HandleFunc("/tips", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if err := tmpl.ExecuteTemplate(w, "tips.html", LivePageData{APIPrefix: apiPrefix}); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
	})

	mux.HandleFunc("/watch", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		room := strings.TrimSpace(r.URL.Query().Get("room"))
		if room == "" {
			http.Error(w, "missing room query param", http.StatusBadRequest)
			return
		}
		base := strings.TrimSuffix(backendURL, "/")
		apiURL := base + apiPrefix + "/room/viewer-token?room=" + url.QueryEscape(room)
		resp, err := http.Post(apiURL, "application/json", bytes.NewBufferString("{}"))
		if err != nil {
			http.Error(w, "could not reach API", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			http.Error(w, string(body), resp.StatusCode)
			return
		}
		var payload viewerTokenPayload
		if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
			http.Error(w, "invalid API response", http.StatusBadGateway)
			return
		}
		q := url.Values{}
		q.Set("room", payload.RoomName)
		q.Set("token", payload.ViewerToken)
		q.Set("livekit", payload.LivekitWsURL)
		q.Set("mode", "watch")
		http.Redirect(w, r, "/live?"+q.Encode(), http.StatusFound)
	})

	mux.HandleFunc("/watch/private", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		share := strings.TrimSpace(r.URL.Query().Get("share"))
		if share == "" {
			http.Error(w, "missing share query param", http.StatusBadRequest)
			return
		}
		base := strings.TrimSuffix(backendURL, "/")
		apiURL := base + apiPrefix + "/broadcast/private-viewer-token?share=" + url.QueryEscape(share)
		resp, err := http.Post(apiURL, "application/json", bytes.NewBufferString("{}"))
		if err != nil {
			http.Error(w, "could not reach API", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			http.Error(w, string(body), resp.StatusCode)
			return
		}
		var payload viewerTokenPayload
		if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
			http.Error(w, "invalid API response", http.StatusBadGateway)
			return
		}
		q := url.Values{}
		q.Set("room", payload.RoomName)
		q.Set("token", payload.ViewerToken)
		q.Set("livekit", payload.LivekitWsURL)
		q.Set("mode", "watch")
		http.Redirect(w, r, "/live?"+q.Encode(), http.StatusFound)
	})

	mux.HandleFunc("/live", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		q := r.URL.Query()
		if q.Get("room") == "" || q.Get("token") == "" || q.Get("livekit") == "" {
			http.Error(w, "missing required query params: room, token, livekit", http.StatusBadRequest)
			return
		}
		if err := tmpl.ExecuteTemplate(w, "live.html", LivePageData{APIPrefix: apiPrefix}); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
	})

	mux.HandleFunc("/create-room", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		roomName := r.FormValue("room_name")
		if roomName == "" {
			http.Error(w, "room_name is required", http.StatusBadRequest)
			return
		}

		body, _ := json.Marshal(map[string]string{"room_name": roomName})
		req, err := http.NewRequest(
			http.MethodPost,
			strings.TrimSuffix(backendURL, "/")+apiPrefix+"/rooms",
			bytes.NewBuffer(body),
		)
		if err != nil {
			http.Error(w, "failed to build API request", http.StatusInternalServerError)
			return
		}
		req.Header.Set("Content-Type", "application/json")
		if auth := strings.TrimSpace(r.Header.Get("Authorization")); auth != "" {
			req.Header.Set("Authorization", auth)
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			http.Error(w, "failed to create room", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()

		data, _ := io.ReadAll(resp.Body)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(resp.StatusCode)
		_, _ = w.Write(data)
	})

	// Always proxy /api to FastAPI before other routes — ServeMux /api/ matching varies by Go version.
	dispatch := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p := r.URL.Path
		if p == "/api" || strings.HasPrefix(p, "/api/") {
			apiProxy.ServeHTTP(w, r)
			return
		}
		mux.ServeHTTP(w, r)
	})

	mediaPolicy := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Explicitly allow camera/mic for this origin (avoids accidental lockdown from proxies).
		w.Header().Set("Permissions-Policy", "camera=(self), microphone=(self)")
		dispatch.ServeHTTP(w, r)
	})

	log.Printf("Camme frontend listening on :%s (API proxy → %s)", port, backendURL)
	if err := http.ListenAndServe(":"+port, mediaPolicy); err != nil {
		log.Fatal(err)
	}
}
