import { useState } from 'react'
import { Modal, Form, Input, message } from 'antd'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { AuthService } from '../services/generated'
import { useAuthStore } from '../store/useAuthStore'

interface ChangePasswordForm {
  current_password: string
  new_password: string
  confirm: string
}

/**
 * 修改当前用户密码的弹窗。
 *
 * 校验旧密码后提交到自助改密接口；成功后后端会递增 token_version 使旧 token 失效，
 * 故前端主动退出登录并跳转到登录页。
 */
const ChangePasswordModal: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => {
  const { t } = useTranslation(['settings', 'common'])
  const navigate = useNavigate()
  const logout = useAuthStore((state) => state.logout)
  const [form] = Form.useForm<ChangePasswordForm>()
  const [submitting, setSubmitting] = useState(false)

  const handleFinish = async (values: ChangePasswordForm) => {
    if (values.new_password !== values.confirm) {
      message.error(t('settings:mismatch'))
      return
    }
    setSubmitting(true)
    try {
      await AuthService.changePasswordApiV1AuthChangePasswordPost({
        requestBody: {
          current_password: values.current_password,
          new_password: values.new_password,
        },
      })
      message.success(t('settings:success'))
      form.resetFields()
      onClose()
      logout()
      navigate('/login')
    } catch (err) {
      // 400 = 旧密码错误；其他统一提示失败
      const status = (err as { status?: number }).status
      message.error(status === 400 ? t('settings:wrongCurrent') : t('settings:failed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={t('settings:title')}
      open={open}
      onCancel={onClose}
      confirmLoading={submitting}
      okText={t('common:save')}
      onOk={() =>
        void form
          .validateFields()
          .then(() => form.submit())
          .catch(() => {})
      }
      destroyOnClose
    >
      <Form form={form} layout="vertical" onFinish={(v) => void handleFinish(v)}>
        <Form.Item
          name="current_password"
          label={t('settings:currentPassword')}
          rules={[{ required: true, message: t('settings:validation.currentRequired') }]}
        >
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="new_password"
          label={t('settings:newPassword')}
          rules={[
            { required: true, message: t('settings:validation.newRequired') },
            { min: 6, message: t('settings:validation.newMin') },
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label={t('settings:confirmPassword')}
          rules={[{ required: true, message: t('settings:validation.confirmRequired') }]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default ChangePasswordModal
