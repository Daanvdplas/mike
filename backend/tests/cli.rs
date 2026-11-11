use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

struct Server(Child);
impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn get(address: SocketAddr, path: &str) -> String {
    let mut connection = TcpStream::connect_timeout(&address, Duration::from_secs(1)).unwrap();
    connection
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    write!(
        connection,
        "GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
    )
    .unwrap();
    let mut response = String::new();
    connection.read_to_string(&mut response).unwrap();
    response
}

#[test]
fn server_without_a_database_serves_real_http_503_and_its_openapi_contract() {
    let directory = tempfile::tempdir().unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    let child = Command::new(env!("CARGO_BIN_EXE_texas-case-finder"))
        .arg("serve")
        .env("ADAMI_DB_PATH", directory.path().join("missing.sqlite3"))
        .env(
            "ADAMI_CACHE_DIR",
            directory.path().join("no-model-download"),
        )
        .env("ADAMI_BIND_ADDR", address.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut server = Server(child);
    let started = Instant::now();
    loop {
        if TcpStream::connect_timeout(&address, Duration::from_millis(50)).is_ok() {
            break;
        }
        assert!(
            server.0.try_wait().unwrap().is_none(),
            "Server exited before exposing readiness."
        );
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "Server did not bind within five seconds."
        );
        std::thread::sleep(Duration::from_millis(20));
    }
    let health = get(address, "/api/health");
    assert!(health.starts_with("HTTP/1.1 503"), "{health}");
    assert!(health.contains("index_unavailable"));
    let contract = get(address, "/openapi.json");
    assert!(contract.starts_with("HTTP/1.1 200"));
    assert!(contract.contains("\"openapi\":\"3.0.3\""));
    assert!(
        !directory.path().join("no-model-download").exists(),
        "Missing storage should not initialize a model."
    );
}

#[test]
fn unknown_cli_commands_exit_unsuccessfully() {
    let output = Command::new(env!("CARGO_BIN_EXE_texas-case-finder"))
        .arg("unknown")
        .output()
        .unwrap();
    assert!(!output.status.success());
}
