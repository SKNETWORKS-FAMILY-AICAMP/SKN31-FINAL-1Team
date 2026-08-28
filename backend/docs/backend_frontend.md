# 백엔드, 프론트 엔드 연동

## 1. 프론트엔드 서버 실행
```
1. 프론트엔드 폴더로 이동
`cd frontend`

2. 어떤 npm을 사용 중인지 확인
`which npm`

* 출력 결과가 /mnt/c/Program Files/... 처럼 /mnt/c/로 시작한다면 Windows용 패키지가 리눅스 환경에서 억지로 실행되면서 경로 충돌을 일으키고 있는 상태

3. 리눅스 자체에 Node.js를 설치
* NVM(Node 버전 관리자) 설치
`curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash`
* 환경 변수 즉시 적용
`source ~/.bashrc`
* 리눅스용 Node.js(LTS 버전) 설치
`nvm install --lts`
4. 설치 확인 및 기존 node_modules 재설치
* 설치가 끝난 후 아래 명령어를 실행해 경로가 /home/playdata/...로 바꼈는지 확인
`which npm`
5. 기존 찌꺼기 파일 삭제
`rm -rf node_modules package-lock.json`
6. 패키지 재설치
`npm install`
7. 서버 실행(기본 포트 3000)
`npm run dev`
8. 웹 실행
`http://localhost:3000`

## 2. 백엔드 서버 실행