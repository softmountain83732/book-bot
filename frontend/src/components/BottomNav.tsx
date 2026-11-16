// frontend/src/components/BottomNav.tsx
import React from 'react';
import { NavLink } from 'react-router-dom';
import { Home, Compass, Heart, PlusCircle, BookOpen, User } from 'lucide-react';
import { useTelegram } from '../hooks/useTelegram';

export const BottomNav: React.FC = () => {
  const { triggerHaptic } = useTelegram();

  const handleNavClick = () => {
    triggerHaptic('light');
  };

  return (
    <nav className="bottom-nav">
      <NavLink
        to="/"
        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        onClick={handleNavClick}
      >
        <Home size={20} />
        <span>ပင်မ</span>
      </NavLink>

      <NavLink
        to="/browse"
        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        onClick={handleNavClick}
      >
        <Compass size={20} />
        <span>ရှာဖွေမည်</span>
      </NavLink>

      <NavLink
        to="/sell"
        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        onClick={handleNavClick}
      >
        <PlusCircle size={20} />
        <span>ရောင်းမည်</span>
      </NavLink>

      <NavLink
        to="/favorites"
        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        onClick={handleNavClick}
      >
        <Heart size={20} />
        <span>သိမ်းထားမှု</span>
      </NavLink>

      <NavLink
        to="/my-books"
        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        onClick={handleNavClick}
      >
        <BookOpen size={20} />
        <span>စာအုပ်များ</span>
      </NavLink>

      <NavLink
        to="/profile"
        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        onClick={handleNavClick}
      >
        <User size={20} />
        <span>Profile</span>
      </NavLink>
    </nav>
  );
};
