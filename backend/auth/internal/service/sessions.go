package service

import (
	"context"
	"strconv"
	"time"

	"github.com/bytedance/sonic"

	"auth/internal/crypto"
	"auth/internal/ports"
	"auth/internal/types"
)

const refreshTokenTTL = 30 * 24 * time.Hour

type Sessions struct {
	cache  ports.Sessions
	crypto *crypto.Service
}

func NewSessions(cache ports.Sessions, crypt *crypto.Service) *Sessions {
	return &Sessions{cache: cache, crypto: crypt}
}
func (s *Sessions) Issue(ctx context.Context, user *types.User) (types.TokenPair, error) {
	sessionID, err := crypto.GenerateSessionID()
	if err != nil {
		return types.TokenPair{}, err
	}

	accessToken, err := s.crypto.IssueAccessToken(strconv.Itoa(user.ID), sessionID, user.Role)
	if err != nil {
		return types.TokenPair{}, err
	}

	refreshToken, err := crypto.GenerateRefreshToken(sessionID)
	if err != nil {
		return types.TokenPair{}, err
	}

	sessionData, err := sonic.Marshal(types.RefreshSession{
		UserID:    user.ID,
		TokenHash: crypto.HashToken(refreshToken),
	})
	if err != nil {
		return types.TokenPair{}, err
	}

	if err := s.cache.Set(ctx, "refresh:"+sessionID, string(sessionData), refreshTokenTTL); err != nil {
		return types.TokenPair{}, err
	}
	if err := s.cache.SAdd(ctx, "user_sessions:"+strconv.Itoa(user.ID), sessionID); err != nil {
		_ = s.cache.Delete(ctx, "refresh:"+sessionID)
		return types.TokenPair{}, err
	}

	return types.TokenPair{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		ExpiresIn:    int(crypto.AccessTokenTTL.Seconds()),
	}, nil
}

func (s *Sessions) RevokeAll(ctx context.Context, userID int) (int, error) {
	userIDStr := strconv.Itoa(userID)
	sessions, err := s.cache.SMembers(ctx, "user_sessions:"+userIDStr)
	if err != nil {
		return 0, err
	}
	for _, sid := range sessions {
		if err := s.cache.Delete(ctx, "refresh:"+sid); err != nil {
			return 0, err
		}
		if err := s.cache.Set(ctx, "blacklist:"+sid, "1", crypto.AccessTokenTTL); err != nil {
			return 0, err
		}
	}
	if err := s.cache.Delete(ctx, "user_sessions:"+userIDStr); err != nil {
		return 0, err
	}
	return len(sessions), nil
}
