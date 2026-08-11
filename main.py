from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from pprint import pprint
import sys
import os
import gogrepoc
import uvicorn


app = FastAPI(title="GOG Repo API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class UpdateRequest(BaseModel):
    os_list: List[str] = []
    lang_list: List[str] = []
    skipknown: bool = False
    updateonly: bool = False
    full: bool = True
    ids: List[str] = []
    skipids: List[str] = []
    skiphidden: bool = False
    installers: str = "standalone"
    resumemode: str = "noresume"
    strictverify: bool = False
    strictdupe: bool = False
    lenientdownloadsupdate: bool = True
    strictextrasupdate: bool = False
    md5xmls: bool = False
    nochangelogs: bool = True


class DownloadRequest(BaseModel):
    savedir: str
    skipextras: bool = True
    skipids: List[str] = []
    dryrun: bool = False
    ids: List[str] = []
    os_list: List[str] = []
    lang_list: List[str] = []
    skipgalaxy: bool = True
    skipstandalone: bool = False
    skipshared: bool = False
    skipfiles: List[str] = []
    covers: bool = False
    backgrounds: bool = False
    skippreallocation: bool = False
    clean_old_images: bool = True
    downloadlimit: Optional[float] = None
    compress_downloads: bool = False


class AddRequest(BaseModel):
    ids: List[str]
    savedir: str


@app.post("/login")
async def login(request: LoginRequest):
    try:
        gogrepoc.cmd_login(request.username, request.password)
        return {"status": "success", "message": "Login successful"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/update")
async def update(request: UpdateRequest):
    try:
        gogrepoc.cmd_update(
            request.os_list,
            request.lang_list,
            request.skipknown,
            request.updateonly,
            not request.full,
            request.ids,
            request.skipids,
            request.skiphidden,
            request.installers,
            request.resumemode,
            request.strictverify,
            request.strictdupe,
            request.lenientdownloadsupdate,
            request.strictextrasupdate,
            request.md5xmls,
            request.nochangelogs,
        )
        return {"status": "success", "message": "Update completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/download")
async def download(request: DownloadRequest):
    try:
        gogrepoc.cmd_download(
            request.savedir,
            request.skipextras,
            request.skipids,
            request.dryrun,
            request.ids,
            request.os_list,
            request.lang_list,
            request.skipgalaxy,
            request.skipstandalone,
            request.skipshared,
            request.skipfiles,
            request.covers,
            request.backgrounds,
            request.skippreallocation,
            request.clean_old_images,
            request.downloadlimit,
        )

        if request.compress_downloads:
            gogrepoc.compress_games(request.savedir)
            return {
                "status": "success",
                "message": "Download and compression completed successfully",
            }

        return {"status": "success", "message": "Download completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/manifest")
async def get_manifest():
    try:
        manifest = gogrepoc.load_manifest()
        downloaded_manifest = gogrepoc.load_downloaded_games()

        # Compare both manifests to find downloaded games
        # if a game exists in the downloaded manifest, remove it from the main manifest
        for game in downloaded_manifest:
            game_id = game.id
            if game_id:
                for m in manifest:
                    if m.id == game_id:
                        manifest.remove(m)
                        break

        # Convert the manifest items to a simpler format for the frontend
        # Format the title by replacing underscores with spaces and capitalizing each word
        games = [
            {
                "id": game.id,
                "title": " ".join(
                    word.capitalize() for word in game.title.replace("_", " ").split()
                ),
            }
            for game in manifest
        ]
        downloaded_games = [
            {
                "id": game.id,
                "title": " ".join(
                    word.capitalize() for word in game.title.replace("_", " ").split()
                ),
                "selectable": "False",
            }
            for game in downloaded_manifest
        ]

        return {
            "status": "success",
            "available_games": games,
            "downloaded_games": downloaded_games,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/check-auth")
async def check_auth():
    try:
        gogrepoc.makeGOGSession()
        # If we get here, the token is valid
        return {"status": "success", "isAuthenticated": True}
    except Exception as e:
        return {"status": "error", "isAuthenticated": False, "detail": str(e)}


@app.post("/add_without_download")
async def add_without_download(request: AddRequest):
    try:
        gogrepoc.add_games_without_download(request.ids, request.savedir)
        return {"status": "success", "message": "Games added without download"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
