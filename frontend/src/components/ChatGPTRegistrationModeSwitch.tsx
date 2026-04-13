import { Space, Switch, Tag, Typography } from 'antd'

import {
  CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
  CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
  type ChatGPTRegistrationMode,
} from '@/lib/chatgptRegistrationMode'
import { useText } from '@/lib/uiLanguage'

const { Text } = Typography

type ChatGPTRegistrationModeSwitchProps = {
  mode: ChatGPTRegistrationMode
  onChange: (mode: ChatGPTRegistrationMode) => void
}

export function ChatGPTRegistrationModeSwitch({
  mode,
  onChange,
}: ChatGPTRegistrationModeSwitchProps) {
  const hasRefreshTokenSolution =
    mode === CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN
  const t = useText()

  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Space align="center" wrap>
        <Switch
          checked={hasRefreshTokenSolution}
          checkedChildren={t('有 RT', 'With RT')}
          unCheckedChildren={t('无 RT', 'No RT')}
          onChange={(checked) =>
            onChange(
              checked
                ? CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN
                : CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
            )
          }
        />
        <Tag color={hasRefreshTokenSolution ? 'success' : 'default'}>
          {hasRefreshTokenSolution ? t('默认推荐', 'Recommended') : t('兼容旧方案', 'Legacy compatible')}
        </Tag>
      </Space>
      <Text type="secondary">
        {hasRefreshTokenSolution
          ? t('有 RT 方案会走新 PR 链路，产出 Access Token + Refresh Token。', 'The RT flow uses the new PR chain and outputs Access Token + Refresh Token.')
          : t('无 RT 方案会走当前旧链路，只产出 Access Token / Session，依赖 RT 的能力可能不可用。', 'The non-RT flow uses the legacy chain and only outputs Access Token / Session. RT-dependent features may be unavailable.')}
      </Text>
    </Space>
  )
}
