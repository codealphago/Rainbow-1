from collections import deque
import random
import atari_py
import torch
import cv2  # Note that importing cv2 before torch may cause segfaults?


class Env():
  def __init__(self, args):
    super().__init__()
    self.dtype = torch.cuda.FloatTensor if args.cuda else torch.FloatTensor
    self.ale = atari_py.ALEInterface()
    self.ale.setInt('random_seed', args.seed)
    self.ale.setInt('max_num_frames', args.max_episode_length)
    self.ale.setFloat('repeat_action_probability', 0)  # Disable sticky actions
    self.ale.setInt('frame_skip', 4)
    self.ale.setBool('color_averaging', True)  # TODO: Should input max (not mean) over last 2 frames of 4
    self.ale.loadROM(atari_py.get_game_path(args.game))  # ROM loading must be done after setting options
    actions = self.ale.getMinimalActionSet()
    self.actions = dict([i, e] for i, e in zip(range(len(actions)), actions))
    self.lives = 0  # Life counter (used in DeepMind training)
    self.life_termination = False  # Used to check if resetting only from loss of life
    self.window = args.history_length  # Number of frames to concatenate
    self.buffer = deque([], maxlen=args.history_length)
    self.screen = [[0] * 160] * 210  # Screen for rendering
    self.training = True  # Consistent with model training mode

  def _get_state(self):
    self.screen = self.ale.getScreenGrayscale()
    state = cv2.resize(self.screen, (84, 84), interpolation=cv2.INTER_AREA)  # Downsample with an appropriate interpolation algorithm
    return self.dtype(state).div_(255)

  def _reset_buffer(self):
    for _ in range(self.window):
      self.buffer.append(self.dtype(84, 84).zero_())

  def reset(self):
    if self.life_termination:
      self.life_termination = False  # Reset flag
      self.ale.act(0)  # Use a no-op after loss of life
    else:
      # Reset internals
      self._reset_buffer()
      self.ale.reset_game()
      # Perform up to 30 random no-ops before starting
      for _ in range(random.randrange(30)):
        self.ale.act(0)  # Assumes raw action 0 is always no-op
        if self.ale.game_over():
          self.ale.reset_game()
    # Process and return "initial" state
    observation = self._get_state()
    self.buffer.append(observation)
    self.lives = self.ale.lives()
    return torch.stack(self.buffer, 0)

  def step(self, action):
    # Process state
    reward = self.ale.act(self.actions.get(action))
    observation = self._get_state()
    self.buffer.append(observation)
    done = self.ale.game_over()
    # Detect loss of life as terminal in training mode
    if self.training:
      lives = self.ale.lives()
      if lives < self.lives:
        self.life_termination = not done  # Only set flag when not truly done
        done = True
      self.lives = lives
    # Return state, reward, done
    return torch.stack(self.buffer, 0), reward, done

  # Uses loss of life as terminal signal
  def train(self):
    self.training = True

  # Uses standard terminal signal
  def eval(self):
    self.training = False

  def action_space(self):
    return len(self.actions)

  def render(self):
    cv2.imshow('screen', self.screen)
    cv2.waitKey(1)

  def close(self):
    cv2.destroyAllWindows()
