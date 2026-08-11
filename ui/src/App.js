import React, { useState, useEffect } from "react";
import {
  Container,
  Form,
  Button,
  Alert,
  ListGroup,
  Row,
  Col,
  Modal,
} from "react-bootstrap";
import axios from "axios";

// Configure axios defaults
const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
axios.defaults.baseURL = apiUrl;
axios.defaults.withCredentials = true;

// Add custom dark mode styles
const darkModeStyles = `
  .list-group-item {
    background-color: #2b3035;
    border-color: #373b3e;
    color: #e9ecef;
  }
  .list-group-item:hover {
    background-color: #343a40;
  }
  .list-group-item.active {
    background-color: #0d6efd;
    border-color: #0d6efd;
  }
  .list-group-item.disabled {
    background-color: #1a1d20;
    color: #6c757d;
  }
  .form-control {
    background-color: #2b3035;
    border-color: #373b3e;
    color: #e9ecef;
  }
  .form-control:focus {
    background-color: #2b3035;
    border-color: #565e64;
    color: #e9ecef;
  }
  .form-check-input {
    background-color: #2b3035;
    border-color: #373b3e;
  }
  .form-check-label {
    color: #e9ecef;
  }
`;

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [availableGames, setAvailableGames] = useState([]);
  const [downloadedGames, setDownloadedGames] = useState([]); // Already downloaded games from the server
  const [gamesToDownload, setGamesToDownload] = useState([]); // Games marked for download
  const [selectedAvailableGames, setSelectedAvailableGames] = useState([]);
  const [selectedToDownloadGames, setSelectedToDownloadGames] = useState([]);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [savedir, setSavedir] = useState("C:/Games/GOG");
  const [compressDownloads, setCompressDownloads] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedGamesToAdd, setSelectedGamesToAdd] = useState([]);

  // Check authentication and load games list on component mount
  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const response = await axios.get("/check-auth");
      if (response.data.isAuthenticated) {
        setIsAuthenticated(true);
        fetchGames();
      }
    } catch (err) {
      setError("Not authenticated. Please login.");
      setIsAuthenticated(false);
    }
  };

  const fetchGames = async () => {
    try {
      const response = await axios.get("/manifest");
      setAvailableGames(response.data.available_games);
      setDownloadedGames(response.data.downloaded_games || []);
      setSelectedToDownloadGames([]);
      setGamesToDownload([]);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load games");
    }
  };

  const handleMoveToDownload = () => {
    if (selectedAvailableGames.length === 0) return;

    setGamesToDownload([...gamesToDownload, ...selectedAvailableGames]);
    setAvailableGames(
      availableGames.filter(
        (game) =>
          !selectedAvailableGames.some((selected) => selected.id === game.id)
      )
    );
    setSelectedAvailableGames([]);

    // Sort games to download by title
    setGamesToDownload((prevGames) =>
      [...prevGames].sort((a, b) => a.title.localeCompare(b.title))
    );
  };

  const handleMoveToAvailable = () => {
    if (selectedToDownloadGames.length === 0) return;

    setAvailableGames([...availableGames, ...selectedToDownloadGames]);
    setGamesToDownload(
      gamesToDownload.filter(
        (game) =>
          !selectedToDownloadGames.some((selected) => selected.id === game.id)
      )
    );
    setSelectedToDownloadGames([]);

    // Sort available games by title
    setAvailableGames((prevGames) =>
      [...prevGames].sort((a, b) => a.title.localeCompare(b.title))
    );
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const response = await axios.post("/login", { username, password });
      setMessage(response.data.message);
      setError(null);
      // After successful login, check auth status and fetch games
      await checkAuth();
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed");
    }
  };

  const handleUpdate = async () => {
    try {
      setMessage("Updating game list. Please watch the console for details...");
      const response = await axios.post("/update", {
        os_list: ["windows"], // You might want to make this configurable
        lang_list: ["en"],
      });
      setMessage(response.data.message);
      fetchGames(); // Refresh the games list
    } catch (err) {
      setError(err.response?.data?.detail || "Update failed");
    }
  };

  const handleAddWithoutDownload = async () => {
    try {
      const selectedIds = selectedGamesToAdd.map((game) => game.id.toString());
      const response = await axios.post("/add_without_download", {
        ids: selectedIds,
        savedir: savedir,
      });
      setMessage(response.data.message);
      fetchGames(); // Refresh the games list
      setShowAddModal(false);
      setSelectedGamesToAdd([]);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to add games");
    }
  };

  const handleDownload = async () => {
    try {
      setDownloading(true);
      setMessage("Starting download. Please watch the console for details...");

      const selectedIds = gamesToDownload.map((game) => game.id.toString());

      const response = await axios.post("/download", {
        savedir: savedir,
        os_list: ["windows"],
        lang_list: ["en"],
        ids: selectedIds,
        compress_downloads: compressDownloads,
      });
      setMessage(response.data.message);
    } catch (err) {
      setError(err.response?.data?.detail || "Download failed");
    } finally {
      setDownloading(false);
      fetchGames();
    }
  };

  useEffect(() => {
    // Set dark theme on body when component mounts
    document.body.setAttribute("data-bs-theme", "dark");
    return () => {
      // Clean up when component unmounts
      document.body.removeAttribute("data-bs-theme");
    };
  }, []);

  return (
    <Container className="mt-5">
      <style>{darkModeStyles}</style>
      <h1 className="text-light">GOG Installers Downloader</h1>

      {error && (
        <Alert variant="danger" dismissible>
          {error}
        </Alert>
      )}
      {message && (
        <Alert variant="success" dismissible>
          {message}
        </Alert>
      )}

      {!isAuthenticated && (
        <Form onSubmit={handleLogin} className="mb-4">
          <Form.Group className="mb-3">
            <Form.Label>GOG Email</Form.Label>
            <Form.Control
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </Form.Group>

          <Form.Group className="mb-3">
            <Form.Label>Password</Form.Label>
            <Form.Control
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Form.Group>

          <Button type="submit">Login</Button>
        </Form>
      )}
      {isAuthenticated && (
        <>
          <Row className="mt-4">
            <Col>
              <h4>{`Available Games (${availableGames.length})`}</h4>
              <ListGroup style={{ height: "400px", overflow: "auto" }}>
                {availableGames.map((game) => (
                  <ListGroup.Item
                    key={game.id}
                    active={selectedAvailableGames.some(
                      (selected) => selected.id === game.id
                    )}
                    action
                    onClick={() => {
                      const isSelected = selectedAvailableGames.some(
                        (selected) => selected.id === game.id
                      );
                      if (isSelected) {
                        setSelectedAvailableGames(
                          selectedAvailableGames.filter(
                            (selected) => selected.id !== game.id
                          )
                        );
                      } else {
                        setSelectedAvailableGames([
                          ...selectedAvailableGames,
                          game,
                        ]);
                      }
                    }}
                  >
                    {game.title}
                  </ListGroup.Item>
                ))}
              </ListGroup>
            </Col>

            <Col
              xs="auto"
              className="d-flex flex-column justify-content-center gap-2"
            >
              <Button
                onClick={handleMoveToDownload}
                disabled={selectedAvailableGames.length === 0}
              >
                &gt;&gt;
              </Button>
              <Button
                onClick={handleMoveToAvailable}
                disabled={selectedToDownloadGames.length === 0}
              >
                &lt;&lt;
              </Button>
            </Col>

            <Col>
              <h4>Games Queue</h4>
              <div className="mb-2">
                <h6>To Download</h6>
                <ListGroup style={{ height: "200px", overflow: "auto" }}>
                  {gamesToDownload.map((game) => (
                    <ListGroup.Item
                      key={game.id}
                      active={selectedToDownloadGames.some(
                        (selected) => selected.id === game.id
                      )}
                      action
                      onClick={() => {
                        const isSelected = selectedToDownloadGames.some(
                          (selected) => selected.id === game.id
                        );
                        if (isSelected) {
                          setSelectedToDownloadGames(
                            selectedToDownloadGames.filter(
                              (selected) => selected.id !== game.id
                            )
                          );
                        } else {
                          setSelectedToDownloadGames([
                            ...selectedToDownloadGames,
                            game,
                          ]);
                        }
                      }}
                    >
                      {game.title}
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              </div>

              <div>
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <h6 className="m-0">{`Already Downloaded (${downloadedGames.length})⬇️`}</h6>
                  <span
                    className="text-muted"
                    style={{
                      cursor: "pointer",
                      fontSize: "0.9em",
                      transition: "all 0.2s ease",
                      ":hover": { textDecoration: "underline" },
                    }}
                    onMouseEnter={(e) =>
                      (e.target.style.textDecoration = "underline")
                    }
                    onMouseLeave={(e) =>
                      (e.target.style.textDecoration = "none")
                    }
                    onClick={() => setShowAddModal(true)}
                  >
                    Need to add games to this list?
                  </span>
                </div>

                <Modal
                  show={showAddModal}
                  onHide={() => {
                    setShowAddModal(false);
                    setSelectedGamesToAdd([]);
                  }}
                  size="lg"
                >
                  <Modal.Header closeButton>
                    <Modal.Title>Add Games to Downloaded List</Modal.Title>
                  </Modal.Header>
                  <Modal.Body>
                    <p className="text-muted mb-3">
                      Select games that you've already downloaded to add them to
                      your downloaded games list.
                    </p>
                    <ListGroup style={{ maxHeight: "400px", overflow: "auto" }}>
                      {availableGames.map((game) => (
                        <ListGroup.Item
                          key={game.id}
                          action
                          active={selectedGamesToAdd.some(
                            (selected) => selected.id === game.id
                          )}
                          onClick={() => {
                            const isSelected = selectedGamesToAdd.some(
                              (selected) => selected.id === game.id
                            );
                            if (isSelected) {
                              setSelectedGamesToAdd(
                                selectedGamesToAdd.filter(
                                  (selected) => selected.id !== game.id
                                )
                              );
                            } else {
                              setSelectedGamesToAdd([
                                ...selectedGamesToAdd,
                                game,
                              ]);
                            }
                          }}
                        >
                          {game.title}
                        </ListGroup.Item>
                      ))}
                    </ListGroup>
                  </Modal.Body>
                  <Modal.Footer>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setShowAddModal(false);
                        setSelectedGamesToAdd([]);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="primary"
                      onClick={handleAddWithoutDownload}
                      disabled={selectedGamesToAdd.length === 0}
                    >
                      Add Selected Games ({selectedGamesToAdd.length})
                    </Button>
                  </Modal.Footer>
                </Modal>

                <ListGroup style={{ height: "200px", overflow: "auto" }}>
                  {downloadedGames.map((game) => (
                    <ListGroup.Item key={game.id} disabled>
                      {game.title}
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              </div>
            </Col>
          </Row>

          <Row className="mt-4">
            <div style={{ display: "flex", justifyContent: "space-evenly" }}>
              <Button onClick={handleUpdate} variant="info">
                Update List
              </Button>
              <div className="d-flex align-items-center gap-2">
                <span>Download Path:</span>
                <Form.Group style={{ width: "300px" }} className="m-0">
                  <Form.Control
                    type="text"
                    value={savedir}
                    onChange={(e) => setSavedir(e.target.value)}
                    placeholder="Enter download path (e.g., C:/Games/GOG)"
                  />
                </Form.Group>
              </div>
              <div>
                <div className="d-flex flex-column gap-2">
                  <Button
                    onClick={handleDownload}
                    variant="success"
                    disabled={downloading}
                  >
                    {downloading ? "Downloading..." : "Download Games"}
                  </Button>
                  <Form.Check
                    type="checkbox"
                    id="compress-downloads"
                    label="Compress downloads?"
                    checked={compressDownloads}
                    onChange={(e) => setCompressDownloads(e.target.checked)}
                  />
                </div>
              </div>
            </div>
          </Row> 
        </>
      )}
    </Container>
  );
}

export default App;
