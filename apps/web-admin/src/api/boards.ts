// 게시판 설정과 게시물 요청. 만들기는 멱등키를 싣고 고치기는 읽은 버전을 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { deleteJson, postJson, putJson } from './http';

export type BoardSetting = Schemas['BoardSetting'];
export type BoardSettingUpdate = Schemas['BoardSettingUpdate'];
export type AdminPost = Schemas['AdminPost'];
export type AdminPostWrite = Schemas['AdminPostWrite'];

const id = encodeURIComponent;

export const updateBoard = (boardKey: string, body: BoardSettingUpdate) => putJson<BoardSetting>(`/boards/${id(boardKey)}`, body);
export const createPost = (body: AdminPostWrite, key: string) => postJson<AdminPost>('/posts', body, { headers: { 'Idempotency-Key': key } });
export const updatePost = (postId: string, body: AdminPostWrite, version: number) => putJson<AdminPost>(`/posts/${id(postId)}`, { ...body, version });
export const deletePost = (postId: string) => deleteJson(`/posts/${id(postId)}`);